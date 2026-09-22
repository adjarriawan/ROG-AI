"""SQL_Query — read-only SQL against an allowlist of tables.

Defence in depth: this validator is the second layer. The first is the
rag_readonly database role plus default_transaction_read_only in database.py.
"""

import re

from langchain_core.tools import tool
from sqlalchemy import text

from database import readonly_engine

ALLOWED_TABLES = {"chat_history", "documents"}
MAX_ROWS = 50

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke|copy|"
    r"vacuum|call|do|merge|comment|reindex|refresh|pg_read_file|pg_sleep|"
    r"lo_import|lo_export|set|reset)\b",
    re.IGNORECASE,
)
_TABLE_REF = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)", re.IGNORECASE)
_CTE_NAME = re.compile(r"(?:\bwith\s+|,)\s*([a-zA-Z_]\w*)\s+as\s*\(", re.IGNORECASE)

SCHEMA_HINT = """Tabel yang tersedia:
- chat_history(id, session_id, role, message, created_at)
- documents(id, filename, content, metadata, created_at)"""


class UnsafeQuery(ValueError):
    pass


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def validate(sql: str) -> str:
    """Return the normalised query, or raise UnsafeQuery."""
    cleaned = strip_comments(sql).strip().rstrip(";").strip()
    if not cleaned:
        raise UnsafeQuery("Query kosong.")
    if ";" in cleaned:
        raise UnsafeQuery("Hanya satu statement yang diizinkan.")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise UnsafeQuery("Hanya SELECT yang diizinkan.")
    if _FORBIDDEN.search(cleaned):
        raise UnsafeQuery("Query mengandung operasi yang tidak diizinkan.")

    referenced = {t.split(".")[-1].lower() for t in _TABLE_REF.findall(cleaned)}
    if not referenced:
        raise UnsafeQuery("Query tidak mereferensikan tabel yang dikenal.")
    # CTE names are not tables; their bodies are checked by the same pass.
    known = ALLOWED_TABLES | {c.lower() for c in _CTE_NAME.findall(cleaned)}
    if not referenced <= known:
        blocked = ", ".join(sorted(referenced - known))
        raise UnsafeQuery(f"Tabel tidak diizinkan: {blocked}")
    return cleaned


def run_query(sql: str) -> str:
    query = validate(sql)
    with readonly_engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.fetchmany(MAX_ROWS)
        cols = list(result.keys())
    if not rows:
        return "Query berhasil, tetapi tidak ada baris yang cocok."
    header = " | ".join(cols)
    body = "\n".join(" | ".join("" if v is None else str(v) for v in r) for r in rows)
    return f"{header}\n{body}"


@tool
def sql_query(query: str) -> str:
    """Jalankan SELECT read-only pada database untuk data terstruktur/statistik.

    Tabel yang diizinkan hanya chat_history dan documents.
    chat_history(id, session_id, role, message, created_at)
    documents(id, filename, content, metadata, created_at)
    Contoh: SELECT count(*) FROM chat_history WHERE created_at::date = CURRENT_DATE
    """
    try:
        return run_query(query)
    except UnsafeQuery as exc:
        return f"Query ditolak: {exc}\n\n{SCHEMA_HINT}"
    except Exception as exc:
        return f"Query gagal dijalankan: {exc}\n\n{SCHEMA_HINT}"
