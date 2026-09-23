import asyncio
import logging
import time
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session

import uploads
from agent import run_agent
from config import get_settings
from database import SessionLocal, get_db
from models import ChatHistory, Document
from schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    DocumentInfo,
    ModelList,
    ServiceHealth,
    SessionInfo,
    Source,
    UploadResponse,
)
from errors import safe_detail
from observability.context import request_id_var
from observability.logging_setup import setup_logging
from services.document_service import ingest
from services.llm_service import list_models

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("agentic_rag")

app = FastAPI(title="Agentic RAG — Local AI System", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request, call_next):
    """Tag every log line of this request with one id.

    The id also goes back in a header and into sanitized error messages, so a
    user-reported failure can be found in the log without them ever seeing the
    underlying exception.
    """
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
        # Logged inside the block: resetting first would strip the id from
        # this very line.
        log.info(
            "%s %s -> %d in %dms",
            request.method,
            request.url.path,
            response.status_code,
            int((time.perf_counter() - started) * 1000),
        )
    finally:
        request_id_var.reset(token)
    response.headers["x-request-id"] = rid
    return response

# Last image uploaded per session, so the agent knows what "this receipt" means.
_last_image: dict[str, str] = {}

HISTORY_TURNS = 10


@app.get("/health", response_model=ServiceHealth)
async def health():
    """Per-dependency health, so a failure points at the culprit.

    Fully async on purpose: a CPU-bound tool call (OCR) saturates the sync
    threadpool that `def` endpoints share, and health must stay answerable
    exactly when the system is struggling.
    """
    import httpx

    def probe_db():
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            return db.execute(
                text("SELECT count(DISTINCT filename) FROM documents")
            ).scalar_one()

    try:
        docs = await asyncio.wait_for(asyncio.to_thread(probe_db), timeout=5)
        database = "ok"
    except Exception as exc:
        log.warning("db health failed: %s", exc)
        database, docs = "error", 0

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            (await client.get(f"{settings.ollama_base_url}/api/tags")).raise_for_status()
        ollama = "ok"
    except Exception as exc:
        log.warning("ollama health failed: %s", exc)
        ollama = "error"

    return ServiceHealth(
        status="ok" if database == "ok" and ollama == "ok" else "degraded",
        database=database,
        ollama=ollama,
        llm_model=settings.ollama_llm_model,
        embedding_model=settings.ollama_embedding_model,
        documents=docs,
    )


@app.get("/models", response_model=ModelList)
def models():
    """Chat models installed in Ollama. Only supports_tools=true can run the agent."""
    try:
        return ModelList(models=list_models(), current=settings.ollama_llm_model)
    except Exception as exc:
        raise HTTPException(
            502, safe_detail("Gagal membaca daftar model dari Ollama.", exc, "models")
        ) from exc


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    recent = (
        db.execute(
            select(ChatHistory)
            .where(ChatHistory.session_id == req.session_id)
            .order_by(ChatHistory.id.desc())
            .limit(HISTORY_TURNS * 2)
        )
        .scalars()
        .all()
    )
    history = list(reversed(recent))

    db.add(ChatHistory(session_id=req.session_id, role="user", message=req.message))
    db.commit()

    try:
        # The agent is blocking (LLM call + possibly a CPU-bound OCR tool).
        # Off-loading it keeps the event loop free to serve /health and others.
        result = await asyncio.to_thread(
            run_agent, req.message, history, _last_image.get(req.session_id), req.model
        )
    except Exception as exc:
        raise HTTPException(
            502, safe_detail("Agent gagal memproses permintaan.", exc, "chat")
        ) from exc

    db.add(ChatHistory(session_id=req.session_id, role="assistant", message=result["answer"]))
    db.commit()

    return ChatResponse(
        answer=result["answer"],
        tool_used=result["tool_used"],
        sources=[Source(**c) for c in _dedupe(result["sources"])],
        model=req.model or settings.ollama_llm_model,
        tools_used=result["tools_used"],
        duration_ms=result["duration_ms"],
    )


def _dedupe(citations):
    """One entry per (file, page) - the UI lists sources, not chunks."""
    seen, out = set(), []
    for c in citations:
        key = (c["filename"], c.get("page"))
        if key in seen:
            continue
        seen.add(key)
        out.append({k: c[k] for k in ("filename", "page", "chunk_index") if k in c})
    return out


@app.post("/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile = File(...),
    session_id: str = Query("default", max_length=100),
    db: Session = Depends(get_db),
):
    # Check the declared size before reading: file.read() pulls the whole body
    # into memory, so validating afterwards is too late to be a limit.
    limit = settings.max_upload_mb * 1024 * 1024
    declared = getattr(file, "size", None)
    if declared is not None and declared > limit:
        raise HTTPException(413, f"File melebihi {settings.max_upload_mb} MB.")
    content = await file.read()
    if len(content) > limit:
        raise HTTPException(413, f"File melebihi {settings.max_upload_mb} MB.")
    try:
        kind, stored_name = uploads.validate(
            file.filename or "", content, file.content_type, settings.max_upload_mb
        )
    except uploads.InvalidUpload as exc:
        raise HTTPException(400, str(exc)) from exc

    path = settings.upload_path / stored_name
    path.write_bytes(content)

    if kind == "image":
        _last_image[session_id] = stored_name
        return UploadResponse(
            filename=file.filename, status="uploaded", kind="image", chunks=0
        )

    try:
        chunks = ingest(db, path, file.filename)
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(
            502, safe_detail("Gagal memproses dokumen.", exc, "upload")
        ) from exc

    if chunks == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "Dokumen tidak memuat teks yang dapat diekstrak.")

    return UploadResponse(
        filename=file.filename, status="processed", kind="document", chunks=chunks
    )


@app.get("/chat/history", response_model=list[ChatMessage])
def chat_history(
    session_id: str = Query(..., max_length=100),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    rows = (
        db.execute(
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


@app.get("/documents", response_model=list[DocumentInfo])
def documents(db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            "SELECT filename, count(*) AS chunks, max(created_at) AS uploaded_at "
            "FROM documents GROUP BY filename ORDER BY uploaded_at DESC"
        )
    ).mappings().all()
    return [DocumentInfo(**r) for r in rows]


@app.delete("/documents/{filename}")
def delete_document(filename: str, db: Session = Depends(get_db)):
    deleted = db.execute(
        text("DELETE FROM documents WHERE filename = :f"), {"f": filename}
    ).rowcount
    db.commit()
    if not deleted:
        raise HTTPException(404, f"Dokumen '{filename}' tidak ada di knowledge base.")
    return {"filename": filename, "deleted_chunks": deleted}


@app.get("/sessions", response_model=list[SessionInfo])
def sessions(db: Session = Depends(get_db)):
    """Chat sessions with their latest message, for the history sidebar."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (session_id)
                   session_id,
                   count(*) OVER (PARTITION BY session_id) AS messages,
                   message AS last_message,
                   created_at AS updated_at
            FROM chat_history
            ORDER BY session_id, created_at DESC
            """
        )
    ).mappings().all()
    return sorted(
        (SessionInfo(**r) for r in rows), key=lambda s: s.updated_at, reverse=True
    )


@app.delete("/chat/history")
def clear_history(session_id: str = Query(..., max_length=100), db: Session = Depends(get_db)):
    deleted = db.execute(
        text("DELETE FROM chat_history WHERE session_id = :s"), {"s": session_id}
    ).rowcount
    db.commit()
    _last_image.pop(session_id, None)
    return {"session_id": session_id, "deleted": deleted}
