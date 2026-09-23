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


def chunk_file(path: Path) -> list[tuple[str, int | None]]:
    """Chunk per page, so each chunk keeps the page it came from.

    Pages used to be joined before splitting, which produced slightly better
    chunks across page breaks but threw away provenance - a citation could
    then only name the file. Page-accurate citations are worth more than the
    few chunks that straddle a boundary.
    """
    out: list[tuple[str, int | None]] = []
    for number, raw in enumerate(load_text(path), start=1):
        page = clean(raw)
        if not page:
            continue
        # TXT/MD arrive as a single "page"; numbering it 1 would be a lie.
        label = number if path.suffix.lower() == ".pdf" else None
        out.extend((c, label) for c in splitter.split_text(page) if c.strip())
    return out

def ingest(db: Session, path: Path, original_name: str) -> int:
    pieces = chunk_file(path)
    if not pieces:
        return 0
    chunks = [c for c, _ in pieces]
    vectors = embed_documents(chunks)
    db.add_all(
        Document(
            filename=original_name,
            content=chunk,
            embedding=vector,
            doc_metadata={
                "filename": original_name,
                "chunk_index": i,
                "page": page,
                "stored_as": path.name,
            },
        )
        for i, ((chunk, page), vector) in enumerate(zip(pieces, vectors))
    )
    db.commit()
    return len(chunks)
