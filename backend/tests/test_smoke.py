"""Runnable checks for the non-trivial logic: SQL guardrails and upload validation."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uploads
from tools.sql_tool import UnsafeQuery, validate

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


def test_chat_history_not_readable():
    """Raw messages are off-limits even though the table exists: with no auth,
    any caller could otherwise steer the agent into another session's chat.
    chat_stats is the aggregate the agent is allowed to see instead."""
    with pytest.raises(UnsafeQuery):
        validate("SELECT message FROM chat_history")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT sum(message_count) FROM chat_stats WHERE day = CURRENT_DATE",
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


# --- Dynamic model selection ---

def test_llm_cached_per_model():
    """Switching models must not hand back the previous model's client."""
    from services.llm_service import get_llm

    a, b = get_llm("qwen2.5:7b"), get_llm("llama3.2:1b")
    assert a is not b
    assert a is get_llm("qwen2.5:7b")  # same name reuses the cached client
    assert (a.model, b.model) == ("qwen2.5:7b", "llama3.2:1b")


def test_executor_cached_per_model():
    from agent import _executors, get_executor

    _executors.clear()
    x = get_executor("qwen2.5:7b")
    assert get_executor("qwen2.5:7b") is x
    assert get_executor("llama3.2:1b") is not x


# --- Citation shaping ---

def test_dedupe_collapses_chunks_of_same_page():
    """Several chunks from one page must surface as a single source."""
    from main import _dedupe

    out = _dedupe(
        [
            {"filename": "a.pdf", "page": 2, "chunk_index": 5, "distance": 0.1},
            {"filename": "a.pdf", "page": 2, "chunk_index": 6, "distance": 0.2},
            {"filename": "a.pdf", "page": 3, "chunk_index": 9, "distance": 0.3},
            {"filename": "b.txt", "page": None, "chunk_index": 0, "distance": 0.4},
        ]
    )
    assert [(c["filename"], c["page"]) for c in out] == [
        ("a.pdf", 2),
        ("a.pdf", 3),
        ("b.txt", None),
    ]
    assert "distance" not in out[0]


def test_sources_survive_a_copied_context():
    """LangChain runs sync tools under contextvars.copy_context(); a .set()
    inside the tool would be discarded. Guards the in-place mutation."""
    import contextvars

    from tools import rag_tool

    rag_tool.reset_sources()

    def inside_tool():
        rag_tool._sources.get().append(
            rag_tool.Citation(filename="x.pdf", page=1, chunk_index=0, distance=0.1)
        )

    contextvars.copy_context().run(inside_tool)
    assert [c["filename"] for c in rag_tool.get_sources()] == ["x.pdf"]
