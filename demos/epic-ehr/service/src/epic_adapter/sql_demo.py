from __future__ import annotations

import re
from pathlib import Path


DATABASE = "OncologiaDemo"
SCHEMA = "oncologia_demo"

STARTER_QUERY = f"""-- {DATABASE} (SQL Server, localhost, Windows authentication)
-- Schema {SCHEMA}: paziente, esame_laboratorio, osservazione_vitale,
-- diagnosi, terapia_farmacologica, ... (Italian names)
-- The agent writes its own read-only query below.
USE {DATABASE};
"""

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|exec|execute|grant|"
    r"revoke|deny|backup|restore|shutdown|kill|dbcc|openrowset|opendatasource|"
    r"openquery|bulk|into|waitfor|reconfigure|sp_\w+|xp_\w+)\b",
    re.IGNORECASE,
)


def validate_select(sql: str) -> str:
    """Allow one read-only SELECT/WITH statement against OncologiaDemo only."""
    text = sql.strip()
    if not text or len(text) > 4000:
        raise ValueError("Query must be 1-4000 characters.")
    if "--" in text or "/*" in text:
        raise ValueError("Comments are not permitted in agent queries.")
    body = text.rstrip(";").strip()
    if ";" in body:
        raise ValueError("Only a single statement is permitted.")
    if not re.match(r"^(select|with)\b", body, re.IGNORECASE):
        raise ValueError("Only SELECT or WITH queries are permitted.")
    if _FORBIDDEN.search(body):
        raise ValueError("The query contains a forbidden keyword.")
    if re.search(r"\b\w+\s*\.\s*\w+\s*\.\s*\w+", body.replace(SCHEMA + ".", "")):
        raise ValueError("Cross-database references are not permitted.")
    return f"USE {DATABASE};\n{body};\n"


def ensure_query(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STARTER_QUERY, encoding="utf-8")
    return path
