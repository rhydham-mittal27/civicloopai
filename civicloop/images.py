"""Look at the first bytes of an upload to learn what it really is, instead of believing the label the sender gave it."""

from __future__ import annotations

ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp", "image/heic")


def sniff_image(content: bytes) -> str | None:
    """The image type of these bytes, or None when they are not a photo we accept (SVG and other formats are refused)."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content[4:8] == b"ftyp" and content[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
        return "image/heic"  # what an iPhone camera produces
    return None
