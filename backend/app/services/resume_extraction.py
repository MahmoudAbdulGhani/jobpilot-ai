"""Bounded local text extraction for already validated resume files."""
from __future__ import annotations

import io
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from importlib.metadata import version

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError


class ExtractionFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parser_identity(extension: str) -> tuple[str | None, str | None]:
    if extension == "pdf":
        return "pypdf", version("pypdf")
    if extension == "docx":
        return "python-docx", version("python-docx")
    return None, None


def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise ExtractionFailure(
            "timeout", "Text extraction took too long. Try a simpler document."
        )


def _append(parts: list[str], value: str, current: int, limit: int) -> int:
    value = value.strip()
    if not value:
        return current
    added = len(value) + (2 if parts else 0)
    if current + added > limit:
        raise ExtractionFailure(
            "output_too_large",
            f"The extracted text exceeds the {limit:,}-character review limit.",
        )
    parts.append(value)
    return current + added


def extract_pdf(
    data: bytes, *, deadline: float, max_chars: int, max_pages: int
) -> tuple[str, str, str]:
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ExtractionFailure(
                "encrypted",
                "Encrypted PDFs cannot be extracted. Upload an unlocked copy.",
            )
        if len(reader.pages) > max_pages:
            raise ExtractionFailure(
                "too_complex",
                f"PDFs are limited to {max_pages} pages for extraction.",
            )
        parts: list[str] = []
        length = 0
        for number, page in enumerate(reader.pages, start=1):
            _check_deadline(deadline)
            text = (
                page.extract_text(extraction_mode="layout") or ""
                if "/Contents" in page
                else ""
            )
            if text.strip():
                length = _append(
                    parts, f"--- Page {number} ---\n{text}", length, max_chars
                )
    except ExtractionFailure:
        raise
    except (
        PdfReadError,
        FileNotDecryptedError,
        ValueError,
        TypeError,
        OSError,
        KeyError,
    ) as error:
        raise ExtractionFailure("malformed", "The PDF could not be parsed safely.") from error
    if not parts:
        raise ExtractionFailure(
            "ocr_required",
            "No extractable text was found. This PDF may be scanned and needs OCR.",
        )
    parser_name, parser_version = parser_identity("pdf")
    return "\n\n".join(parts), parser_name or "pypdf", parser_version or "unknown"


def extract_docx(
    data: bytes, *, deadline: float, max_chars: int, max_blocks: int
) -> tuple[str, str, str]:
    try:
        document = Document(io.BytesIO(data))
        parts: list[str] = []
        length = 0
        blocks = 0
        for item in document.iter_inner_content():
            _check_deadline(deadline)
            blocks += 1
            if blocks > max_blocks:
                raise ExtractionFailure(
                    "too_complex", "The DOCX contains too many paragraphs or tables."
                )
            if isinstance(item, Paragraph):
                length = _append(parts, item.text, length, max_chars)
            elif isinstance(item, Table):
                rows: list[str] = []
                for row in item.rows:
                    blocks += len(row.cells)
                    if blocks > max_blocks:
                        raise ExtractionFailure(
                            "too_complex", "The DOCX contains too many table cells."
                        )
                    rows.append("\t".join(cell.text.strip() for cell in row.cells))
                length = _append(parts, "\n".join(rows), length, max_chars)
    except ExtractionFailure:
        raise
    except (ValueError, KeyError, OSError) as error:
        raise ExtractionFailure("malformed", "The DOCX could not be parsed safely.") from error
    if not parts:
        raise ExtractionFailure("empty", "No readable text was found in this DOCX.")
    parser_name, parser_version = parser_identity("docx")
    return "\n\n".join(parts), parser_name or "python-docx", parser_version or "unknown"


def extract(
    data: bytes,
    extension: str,
    *,
    timeout_seconds: int,
    max_chars: int,
    max_pages: int,
    max_blocks: int,
) -> tuple[str, str, str]:
    deadline = time.monotonic() + timeout_seconds
    if extension == "pdf":
        worker = lambda: extract_pdf(
            data, deadline=deadline, max_chars=max_chars, max_pages=max_pages
        )
    elif extension == "docx":
        worker = lambda: extract_docx(
            data, deadline=deadline, max_chars=max_chars, max_blocks=max_blocks
        )
    else:
        raise ExtractionFailure(
            "unsupported", "This resume format does not support text extraction."
        )

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="resume-extraction")
    future = executor.submit(worker)
    try:
        return future.result(timeout=timeout_seconds)
    except TimeoutError as error:
        future.cancel()
        raise ExtractionFailure(
            "timeout", "Text extraction took too long. Try a simpler document."
        ) from error
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
