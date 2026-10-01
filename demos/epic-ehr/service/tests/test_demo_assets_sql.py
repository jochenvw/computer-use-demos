import tempfile
import unittest
from pathlib import Path

from epic_adapter.file_catalog import FileCatalog
from epic_adapter.sql_demo import validate_select


class SqlValidationTests(unittest.TestCase):
    def test_accepts_single_select_and_scopes_database(self):
        sql = validate_select(
            "SELECT p.mrn FROM oncologia_demo.paziente p WHERE p.mrn = N'TUS-2026-0417';"
        )
        self.assertTrue(sql.startswith("USE OncologiaDemo;\nSELECT"))

    def test_accepts_information_schema_and_cte(self):
        validate_select(
            "SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='oncologia_demo'"
        )
        validate_select("WITH x AS (SELECT 1 AS a) SELECT a FROM x")

    def test_rejects_writes_batches_comments_and_other_databases(self):
        for sql in [
            "DELETE FROM oncologia_demo.paziente",
            "SELECT 1; DROP TABLE oncologia_demo.paziente",
            "SELECT * INTO t FROM oncologia_demo.paziente",
            "SELECT 1 -- hi",
            "SELECT * FROM master.sys.databases",
            "EXEC sp_who",
            "SELECT * FROM OPENROWSET('x','y','z')",
        ]:
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                validate_select(sql)


class SharedAssetTests(unittest.TestCase):
    def test_flat_assets_folder_is_listed_and_openable_for_any_patient(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory) / "assets"
            assets.mkdir()
            (assets / "ecg.jpg").write_bytes(b"\xff\xd8fake")
            (assets / "setup.sql").write_text("SELECT 1")
            catalog = FileCatalog((), (assets,))
            records = catalog.find("TUS-2026-0417")
            self.assertEqual(["ecg.jpg"], [record.name for record in records])
            _, image = catalog.open_for_skill(records[0], "TUS-2026-0417")
            self.assertEqual(b"\xff\xd8fake", image)
            self.assertEqual(
                (assets / "ecg.jpg").resolve(), catalog.verify(records[0], "OTHER")
            )


class TraceTests(unittest.TestCase):
    def test_trace_records_events_and_screenshots(self):
        from epic_adapter.diagnostics import Trace, latest

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = Trace(root, "sql-desktop")
            trace.event("tool", step=1, name="observe")
            trace.screenshot(1, "data:image/jpeg;base64,aGk=")
            [run] = latest(root)
            self.assertEqual(["start", "tool"], [e["event"] for e in run["events"]])
            self.assertEqual(["step-001.jpg"], run["screenshots"])
            Trace(None, "x").event("ignored")
            self.assertEqual([], latest(None))


if __name__ == "__main__":
    unittest.main()
