import logging

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session

import uploads
from agent import run_agent
from config import get_settings
from database import get_db
from models import ChatHistory, Document
from schemas import ChatMessage, ChatRequest, ChatResponse, Source, UploadResponse
from services.document_service import ingest

log = logging.getLogger("agentic_rag")
settings = get_settings()

app = FastAPI(title="Agentic RAG — Local AI System", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Last image uploaded per session, so the agent knows what "this receipt" means.
_last_image: dict[str, str] = {}

HISTORY_TURNS = 10


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
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
        result = run_agent(req.message, history, _last_image.get(req.session_id))
    except Exception as exc:
        log.exception("agent failed")
        raise HTTPException(502, f"Agent gagal memproses permintaan: {exc}") from exc

    db.add(ChatHistory(session_id=req.session_id, role="assistant", message=result["answer"]))
    db.commit()

    return ChatResponse(
        answer=result["answer"],
        tool_used=result["tool_used"],
        sources=[Source(filename=f) for f in result["sources"]],
    )


@app.post("/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile = File(...),
    session_id: str = Query("default", max_length=100),
    db: Session = Depends(get_db),
):
    content = await file.read()
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
        log.exception("ingest failed")
        path.unlink(missing_ok=True)
        raise HTTPException(502, f"Gagal memproses dokumen: {exc}") from exc

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


@app.get("/documents")
def documents(db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            "SELECT filename, count(*) AS chunks, max(created_at) AS uploaded_at "
            "FROM documents GROUP BY filename ORDER BY uploaded_at DESC"
        )
    ).mappings().all()
    return [dict(r) for r in rows]
