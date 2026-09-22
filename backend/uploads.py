"""Upload validation: extension, size, MIME, and file signature (magic bytes)."""

import uuid
from pathlib import Path

DOC_EXT = {".pdf", ".txt", ".md"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

ALLOWED_MIME = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
    ".md": {"text/plain", "text/markdown"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
    ".bmp": {"image/bmp", "image/x-ms-bmp"},
}

_SIGNATURES = {
    ".pdf": [b"%PDF-"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".bmp": [b"BM"],
}


class InvalidUpload(ValueError):
    pass


def kind_of(ext: str) -> str:
    if ext in IMG_EXT:
        return "image"
    if ext in DOC_EXT:
        return "document"
    raise InvalidUpload(f"Ekstensi '{ext}' tidak diizinkan.")


def check_signature(ext: str, head: bytes) -> None:
    if ext == ".webp":
        if not (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
            raise InvalidUpload("Isi file tidak cocok dengan ekstensi .webp.")
        return
    expected = _SIGNATURES.get(ext)
    if expected and not any(head.startswith(sig) for sig in expected):
        raise InvalidUpload(f"Isi file tidak cocok dengan ekstensi {ext}.")
    if ext in {".txt", ".md"}:
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            raise InvalidUpload("File teks harus UTF-8.") from None


def validate(filename: str, content: bytes, content_type: str | None, max_mb: int) -> tuple[str, str]:
    """Return (kind, safe_stored_name) or raise InvalidUpload."""
    ext = Path(filename).suffix.lower()
    kind = kind_of(ext)

    if not content:
        raise InvalidUpload("File kosong.")
    if len(content) > max_mb * 1024 * 1024:
        raise InvalidUpload(f"Ukuran file melebihi {max_mb} MB.")

    if content_type:
        base = content_type.split(";")[0].strip().lower()
        if base not in ALLOWED_MIME[ext] and base != "application/octet-stream":
            raise InvalidUpload(f"MIME type '{base}' tidak cocok dengan {ext}.")

    check_signature(ext, content[:32])
    return kind, f"{uuid.uuid4().hex}{ext}"
