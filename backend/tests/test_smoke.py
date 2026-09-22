"""Runnable checks for the non-trivial logic: SQL guardrails and upload validation."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uploads  # noqa: E402
from tools.sql_tool import UnsafeQuery, validate  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


# --- SEC-001: SQL tool must refuse anything that is not a read ---

@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE documents",
        "DELETE FROM chat_history",
        "UPDATE chat_history SET message = 'x'",
        "SELECT 1 FROM chat_history; DROP TABLE documents",
        "SELECT * FROM users",                      # outside the allowlist
        "SELECT * FROM pg_shadow",                  # system catalog
        "SELECT /* hide */ 1 FROM chat_history; DELETE FROM documents",
        "SELECT * FROM chat_history -- \n; DROP TABLE documents",
        "",
    ],
)
def test_unsafe_sql_rejected(sql):
    with pytest.raises(UnsafeQuery):
        validate(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM chat_history WHERE created_at::date = CURRENT_DATE",
        "select filename from documents limit 5;",
        "WITH t AS (SELECT id FROM documents) SELECT count(*) FROM t JOIN documents ON true",
    ],
)
def test_safe_sql_accepted(sql):
    assert validate(sql)


# --- File upload validation ---

def test_rejects_disallowed_extension():
    with pytest.raises(uploads.InvalidUpload):
        uploads.validate("payload.exe", b"MZ\x00", None, 25)


def test_rejects_signature_mismatch():
    """A .png whose bytes are actually a PDF must not pass."""
    with pytest.raises(uploads.InvalidUpload):
        uploads.validate("fake.png", b"%PDF-1.7 not an image", "image/png", 25)


def test_rejects_oversize():
    with pytest.raises(uploads.InvalidUpload):
        uploads.validate("big.png", PNG + b"\x00" * (2 * 1024 * 1024), "image/png", 1)


def test_rejects_mime_mismatch():
    with pytest.raises(uploads.InvalidUpload):
        uploads.validate("doc.pdf", b"%PDF-1.7", "image/png", 25)


def test_accepts_valid_png_and_renames():
    kind, stored = uploads.validate("receipt.png", PNG, "image/png", 25)
    assert kind == "image"
    assert stored.endswith(".png") and "receipt" not in stored  # sanitised to a uuid


def test_accepts_valid_pdf():
    kind, stored = uploads.validate("policy.pdf", b"%PDF-1.7\n%...", "application/pdf", 25)
    assert (kind, stored.endswith(".pdf")) == ("document", True)
