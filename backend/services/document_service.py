"""Load a PDF/TXT file, chunk it, embed it, store it in pgvector."""

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from models import Document
from services.embedding_service import embed_documents

splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)


def load_text(path: Path) -> list[str]:
    """Return one raw text per source page/section."""
    if path.suffix.lower() == ".pdf":
        docs = PyPDFLoader(str(path)).load()
    else:
        docs = TextLoader(str(path), encoding="utf-8", autodetect_encoding=True).load()
    return [d.page_content for d in docs]


def clean(text: str) -> str:
    return " ".join(text.split())


def chunk_file(path: Path) -> list[str]:
    pages = [clean(t) for t in load_text(path)]
    joined = "\n\n".join(p for p in pages if p)
    return [c for c in splitter.split_text(joined) if c.strip()]


def ingest(db: Session, path: Path, original_name: str) -> int:
    chunks = chunk_file(path)
    if not chunks:
        return 0
    vectors = embed_documents(chunks)
    db.add_all(
        Document(
            filename=original_name,
            content=chunk,
            embedding=vector,
            doc_metadata={
                "filename": original_name,
                "chunk_index": i,
                "stored_as": path.name,
            },
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors))
    )
    db.commit()
    return len(chunks)
