"""
PDF upload validation — runs synchronously in the view, before a file is
ever handed to Celery. Rejects bad input early instead of tying up the
one free background worker on a file that was never going to work (point 10).
"""

import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger("orders.pdf")

MAX_FILE_SIZE_MB = 50
MAX_PAGE_COUNT = 150
PDF_MAGIC_BYTES = b"%PDF-"


class UploadValidationError(Exception):
    """Raised with a student-facing message when an upload fails validation."""


def validate_pdf_upload(uploaded_file):
    """
    Validates an uploaded file before queuing a Celery task.
    Checks, in order: size, actual file signature (not just the .pdf
    extension), that it opens as a real PDF, that it isn't
    password-protected, and that it doesn't exceed a sane page count.
    Returns the page count on success.
    """
    # 1. Size check — cheap, so do it first.
    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise UploadValidationError(
            f"File is {size_mb:.1f} MB; the limit is {MAX_FILE_SIZE_MB} MB."
        )

    # 2. Magic-byte check — catches a .txt or .jpg renamed to .pdf,
    # which a naive `filename.endswith('.pdf')` check would miss.
    header = uploaded_file.read(5)
    uploaded_file.seek(0)
    if header != PDF_MAGIC_BYTES:
        logger.warning("Rejected upload: invalid PDF signature (%r)", header)
        raise UploadValidationError("This file isn't a valid PDF.")

    # 3. Open it for real — catches corrupted files that pass the magic-byte check.
    try:
        reader = PdfReader(uploaded_file)
    except PdfReadError as exc:
        logger.warning("Rejected upload: unreadable PDF (%s)", exc)
        raise UploadValidationError("This PDF appears to be corrupted.") from exc

    # 4. Password-protected PDFs can't be paged/rendered without the password.
    if reader.is_encrypted:
        logger.info("Rejected upload: password-protected PDF")
        raise UploadValidationError(
            "This PDF is password-protected. Please upload an unprotected copy."
        )

    # 5. Page count sanity check.
    page_count = len(reader.pages)
    if page_count > MAX_PAGE_COUNT:
        raise UploadValidationError(
            f"This PDF has {page_count} pages; the limit is {MAX_PAGE_COUNT}."
        )

    uploaded_file.seek(0)
    logger.info("Upload validated: %s pages, %.1f MB", page_count, size_mb)
    return page_count
