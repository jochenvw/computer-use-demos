import tempfile
import unittest
from pathlib import Path

from epic_adapter.file_catalog import FileCatalog


class FileCatalogTests(unittest.TestCase):
    def test_discovers_only_patient_scoped_allowlisted_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patient = root / "DEMO-100042"
            patient.mkdir()
            (patient / "ecg.pdf").write_bytes(b"synthetic")
            (patient / "notes.exe").write_bytes(b"blocked")
            (root / "OTHER-1.pdf").write_bytes(b"other")

            records = FileCatalog((root,)).find("DEMO-100042")

            self.assertEqual(["ecg.pdf"], [record.name for record in records])

    def test_rejects_path_traversal_patient_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                FileCatalog((Path(directory),)).find("..\\secret")

    def test_patient_prefix_does_not_match_other_patients(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other = root / "DEMO-100042-extra"
            other.mkdir()
            (other / "ecg.xml").write_text("synthetic")
            self.assertEqual([], FileCatalog((root,)).find("DEMO-100042"))

    def test_missing_root_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                FileCatalog((Path(directory) / "missing",)).find("DEMO-100042")

    def test_changed_file_is_rejected_on_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patient = root / "DEMO-100042"
            patient.mkdir()
            file = patient / "ecg.xml"
            file.write_text("before")
            catalog = FileCatalog((root,))
            record = catalog.find("DEMO-100042")[0]
            file.write_text("after")
            with self.assertRaises(RuntimeError):
                catalog.verify(record, "DEMO-100042")


if __name__ == "__main__":
    unittest.main()
