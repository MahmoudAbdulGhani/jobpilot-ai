"""Bounded structural validation for uploaded resume files.

Validation looks at the actual file bytes (magic header, container layout),
never at the MIME type supplied by the client. This is format validation, not
malware scanning.
"""
import io
import zipfile
from xml.etree import ElementTree

ALLOWED_EXTENSIONS = {"pdf", "docx"}
MAX_FILENAME_LENGTH = 255

# Structural validation bounds keep container inspection cheap: both the
# number of entries and the archive's total expanded content are capped. The
# required XML parts must also be well formed and contain no DTD/entities.
_MAX_DOCX_ENTRIES = 64
_MAX_EXPANDED_BYTES = 8 * 1024 * 1024

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_DOCX_ENTRY = "word/document.xml"
_CONTENT_TYPES_ENTRY = "[Content_Types].xml"
_CONTENT_TYPES_ROOT = "{http://schemas.openxmlformats.org/package/2006/content-types}Types"
_WORD_DOCUMENT_ROOT = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document"
_WORD_DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
_PDF_HEADER = b"%PDF-"
_PDF_EOF = b"%%EOF"


class _RejectingTreeBuilder(ElementTree.TreeBuilder):
    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise ValueError("DTD declarations are not allowed")


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
            if not names or len(names) > _MAX_DOCX_ENTRIES:
                return False
            if len(names) != len(set(names)):
                return False
            if sum(info.file_size for info in container.infolist()) > _MAX_EXPANDED_BYTES:
                return False
            if _DOCX_ENTRY not in names or _CONTENT_TYPES_ENTRY not in names:
                return False
            content_types = _read_entry_bounded(container, _CONTENT_TYPES_ENTRY)
            if not content_types:
                return False
            if _has_dtd_or_entity(content_types):
                return False
            content_types_root = _parse_xml(content_types)
            if content_types_root is None or content_types_root.tag != _CONTENT_TYPES_ROOT:
                return False
            if not any(
                child.attrib.get("PartName") == "/word/document.xml"
                and child.attrib.get("ContentType") == _WORD_DOCUMENT_CONTENT_TYPE
                for child in content_types_root
            ):
                return False
            document = _read_entry_bounded(container, _DOCX_ENTRY)
            if not document:
                return False
            if _has_dtd_or_entity(document):
                return False
            document_root = _parse_xml(document)
            return document_root is not None and document_root.tag == _WORD_DOCUMENT_ROOT
    except (zipfile.BadZipFile, OSError, ValueError, EOFError):
        return False


def _read_entry_bounded(
    container: zipfile.ZipFile, name: str, cap: int = _MAX_EXPANDED_BYTES
) -> bytes:
    """Return a whole required part when its declared expanded size fits within
    the cap, otherwise reject it (over-limit) without expanding it."""
    try:
        info = container.getinfo(name)
        if info.file_size > cap:
            return b""
        with container.open(name) as entry:
            return entry.read(cap + 1)
    except (KeyError, zipfile.BadZipFile, OSError, ValueError, EOFError):
        return b""


def _has_dtd_or_entity(head: bytes) -> bool:
    upper = head.upper()
    return b"<!DOCTYPE" in upper or b"<!ENTITY" in upper


def _parse_xml(data: bytes) -> ElementTree.Element | None:
    if not data or len(data) > _MAX_EXPANDED_BYTES:
        return None
    try:
        parser = ElementTree.XMLParser(target=_RejectingTreeBuilder())
        return ElementTree.fromstring(data, parser=parser)
    except (ElementTree.ParseError, ValueError, OSError):
        return None
