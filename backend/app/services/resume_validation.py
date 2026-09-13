"""Bounded structural validation for uploaded resume files.

Validation looks at the actual file bytes (magic header, container layout),
never at the MIME type supplied by the client. This is format validation, not
malware scanning.
"""
import io
import zipfile

ALLOWED_EXTENSIONS = {"pdf", "docx"}
MAX_FILENAME_LENGTH = 255

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_DOCX_ENTRY = "word/document.xml"
_CONTENT_TYPES_ENTRY = "[Content_Types].xml"
_PDF_HEADER = b"%PDF-"
_PDF_EOF = b"%%EOF"
_MAX_INSPECT_BYTES = 64 * 1024


def media_type(extension: str) -> str:
    return _MEDIA_TYPES[extension]


def sanitize_filename(filename: str | None) -> str | None:
    """Return only the final path component, devoid of path separators and
    control characters. None means the submitted value cannot be used."""
    if not filename:
        return None
    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(char for char in cleaned if ord(char) >= 32 and char != "\x7f")
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    return cleaned


def extension_of(filename: str) -> str | None:
    if "." not in filename:
        return None
    extension = filename.rsplit(".", 1)[-1].lower()
    return extension or None


def is_allowed_extension(extension: str | None) -> bool:
    return extension in ALLOWED_EXTENSIONS


def is_valid_pdf(data: bytes) -> bool:
    if not data.startswith(_PDF_HEADER) or _PDF_EOF not in data:
        return False
    return True


def is_valid_docx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as container:
            names = container.namelist()
            if not names or _DOCX_ENTRY not in names:
                return False
            content_types = _read_entry_head(container, _CONTENT_TYPES_ENTRY)
            if not content_types:
                return False
            if b"wordprocessingml" not in content_types:
                return False
            document = _read_entry_head(container, _DOCX_ENTRY)
            return bool(document)
    except (zipfile.BadZipFile, OSError, ValueError, EOFError):
        return False


def _read_entry_head(container: zipfile.ZipFile, name: str, limit: int = _MAX_INSPECT_BYTES) -> bytes:
    try:
        with container.open(name) as entry:
            return entry.read(limit)
    except (KeyError, zipfile.BadZipFile, OSError, ValueError, EOFError):
        return b""