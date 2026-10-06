import os
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path

SEED = Path(__file__).resolve().parents[2] / "infra" / "seed-anna-oncologia.sql"
SQLCMD = shutil.which("sqlcmd") or (
    r"C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\SQLCMD.EXE"
)
SERVER = r"(localdb)\MSSQLLocalDB"

# Two plausible shapes of the VM schema: natural keys vs identity keys.
SCHEMAS = {
    "natural": """
CREATE TABLE oncologia_demo.paziente (paziente_id int NOT NULL PRIMARY KEY,
  mrn nvarchar(32) NOT NULL UNIQUE, nome nvarchar(50) NOT NULL, cognome nvarchar(50) NOT NULL,
  sesso char(1) NOT NULL, data_nascita date NOT NULL, comune_residenza nvarchar(80) NULL,
  stato_sintetico nvarchar(20) NOT NULL, creato_il datetime2 NOT NULL, rv rowversion);
CREATE TABLE oncologia_demo.esame_laboratorio (esame_id int NOT NULL PRIMARY KEY,
  paziente_id int NOT NULL REFERENCES oncologia_demo.paziente(paziente_id), data_ora datetime2 NOT NULL,
  codice nvarchar(20) NOT NULL, nome_esame nvarchar(100) NOT NULL, valore_numerico decimal(10,2) NULL,
  valore_testo nvarchar(50) NULL, unita nvarchar(20) NULL, range_basso decimal(10,2) NULL,
  range_alto decimal(10,2) NULL, flag_anomalia nvarchar(5) NULL, laboratorio nvarchar(50) NOT NULL);
INSERT oncologia_demo.paziente (paziente_id, mrn, nome, cognome, sesso, data_nascita,
  comune_residenza, stato_sintetico, creato_il)
  VALUES (7, N'SYN-2026-0001', N'Mario', N'Bianchi', 'M', '1960-01-01', N'Siena', N'sintetico', SYSDATETIME());
INSERT oncologia_demo.esame_laboratorio VALUES (40, 7, '2026-01-01', N'HB', N'Emoglobina', 13, NULL,
  N'g/dL', 13, 17, NULL, N'Lab centrale');
""",
    "identity": """
CREATE TABLE oncologia_demo.paziente (paziente_id int IDENTITY(1,1) PRIMARY KEY,
  mrn nvarchar(32) NOT NULL, nome nvarchar(50) NOT NULL, cognome nvarchar(50) NOT NULL,
  sesso nvarchar(1) NOT NULL, data_nascita date NOT NULL, stato_sintetico bit NOT NULL);
CREATE TABLE oncologia_demo.esame_laboratorio (id bigint IDENTITY(1,1) PRIMARY KEY,
  paziente_id int NOT NULL, data_ora datetime2 NOT NULL, codice nvarchar(20) NOT NULL,
  nome_esame nvarchar(100) NOT NULL, valore_numerico decimal(10,2) NOT NULL,
  valore_testo nvarchar(50) NOT NULL, unita nvarchar(20) NOT NULL, range_basso decimal(10,2) NULL,
  range_alto decimal(10,2) NULL, flag_anomalia bit NOT NULL);
INSERT oncologia_demo.paziente (mrn, nome, cognome, sesso, data_nascita, stato_sintetico)
  VALUES (N'SYN-2026-0001', N'Mario', N'Bianchi', N'M', '1960-01-01', 1),
         (N'SYN-2026-0002', N'Lucia', N'Verdi', N'F', '1950-01-01', 1);
INSERT oncologia_demo.esame_laboratorio (paziente_id, data_ora, codice, nome_esame,
  valore_numerico, valore_testo, unita, flag_anomalia)
  VALUES (2, '2026-01-01', N'HB', N'Emoglobina', 12, N'12', N'g/dL', 0);
CREATE TABLE oncologia_demo.episodio (episodio_id int IDENTITY(1,1) PRIMARY KEY,
  paziente_id int NOT NULL, struttura_id int NOT NULL, uo_id int NULL,
  numero_nosologico nvarchar(50) NULL, tipo_episodio nvarchar(50) NOT NULL,
  regime nvarchar(50) NULL, data_inizio datetime2 NOT NULL, data_fine datetime2 NULL,
  motivo nvarchar(500) NULL, stato nvarchar(30) NOT NULL);
INSERT oncologia_demo.episodio (paziente_id, struttura_id, uo_id, tipo_episodio, data_inizio, stato)
  VALUES (1, 1, 2, N'RICOVERO', '2026-01-01', N'APERTO');
CREATE TABLE oncologia_demo.diagnosi (diagnosi_id int IDENTITY(1,1) PRIMARY KEY,
  paziente_id int NOT NULL, episodio_id int NULL, sistema_codifica nvarchar(50) NOT NULL,
  versione_codifica nvarchar(50) NULL, codice nvarchar(50) NOT NULL,
  descrizione nvarchar(500) NOT NULL, tipo nvarchar(50) NULL, data_diagnosi date NULL,
  attiva bit NOT NULL);
""",
}


def _sqlcmd(*args: str) -> str:
    result = subprocess.run(
        [SQLCMD, "-S", SERVER, "-E", "-b", "-W", "-h", "-1", *args],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


@unittest.skipUnless(
    os.name == "nt" and Path(SQLCMD).is_file() and os.environ.get("EPIC_SKIP_LOCALDB") != "1",
    "LocalDB/sqlcmd not available",
)
class SeedAnnaOncologiaTests(unittest.TestCase):
    def test_seed_is_idempotent_on_both_schema_shapes(self):
        for shape, ddl in SCHEMAS.items():
            database = f"seedtest_{shape}_{uuid.uuid4().hex[:8]}"
            with self.subTest(shape=shape):
                try:
                    _sqlcmd("-Q", f"CREATE DATABASE [{database}]")
                except AssertionError as error:
                    self.skipTest(f"LocalDB unavailable: {error}")
                try:
                    _sqlcmd("-d", database, "-Q", "CREATE SCHEMA oncologia_demo")
                    _sqlcmd("-d", database, "-Q", ddl)
                    first = _sqlcmd("-d", database, "-i", str(SEED))
                    second = _sqlcmd("-d", database, "-i", str(SEED))
                    self.assertIn("TUS-2026-0417 Anna Ricci 1971-03-14 10", first)
                    self.assertIn("TUS-2026-0417 Anna Ricci 1971-03-14 10", second)
                    count, cea = _sqlcmd(
                        "-d", database, "-Q",
                        "SET NOCOUNT ON; SELECT COUNT(*) FROM oncologia_demo.paziente; "
                        "SELECT CONVERT(varchar(10), e.valore_numerico) FROM "
                        "oncologia_demo.esame_laboratorio e JOIN oncologia_demo.paziente p "
                        "ON p.paziente_id = e.paziente_id WHERE p.mrn = N'TUS-2026-0417' "
                        "AND e.codice = N'CEA'",
                    ).split()
                    self.assertEqual({"natural": "2", "identity": "3"}[shape], count)
                    self.assertEqual("18.40", cea)
                    if shape == "identity":
                        clinical = _sqlcmd(
                            "-d", database, "-Q",
                            "SET NOCOUNT ON; SELECT COUNT(*) FROM oncologia_demo.diagnosi d "
                            "JOIN oncologia_demo.episodio e ON e.episodio_id = d.episodio_id "
                            "JOIN oncologia_demo.paziente p ON p.paziente_id = e.paziente_id "
                            "WHERE p.mrn = N'TUS-2026-0417' AND e.numero_nosologico = N'2026/004417'",
                        ).split()
                        self.assertEqual(["4"], clinical)
                finally:
                    _sqlcmd("-Q", f"ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK "
                                  f"IMMEDIATE; DROP DATABASE [{database}]")


if __name__ == "__main__":
    unittest.main()
