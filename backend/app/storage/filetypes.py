"""Recognise file types from their first bytes, not from the name the browser sends."""

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
DOCUMENT_TYPES = {"application/pdf"}


def sniff(head: bytes) -> str | None:
    """Return the content type of a file from its first bytes, or None if not allowed."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def safe_filename(name: str, fallback: str = "file") -> str:
    """Keep a readable, harmless file name for downloads."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in base).strip(" .")
    return cleaned[:120] or fallback
