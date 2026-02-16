"""
Shared Constants
=================
File paths, extension groups, and project-wide constants.
"""

import os

# ── Directory Paths ──────────────────────────────────────────
UPLOAD_DIR = "data/uploads"
AUTOFILL_TEMP_DIR = "data/autofill_temp"
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

# ── File Extension Groups ────────────────────────────────────
DOCUMENT_EXTS = (".pdf", ".docx", ".doc", ".rtf")
TEXT_EXTS = (".txt", ".md", ".markdown")
SPREADSHEET_EXTS = (".xlsx", ".xls", ".csv", ".tsv")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".svg", ".ico", ".jfif")

# All supported file extensions (union of all groups)
ALL_SUPPORTED_EXTS = DOCUMENT_EXTS + TEXT_EXTS + SPREADSHEET_EXTS + IMAGE_EXTS

# ── MIME Types ───────────────────────────────────────────────
MIME_MAP = {
    # Documents
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "rtf": "application/rtf",
    # Spreadsheets
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    # Plain text
    "txt": "text/plain",
    "md": "text/markdown",
    "markdown": "text/markdown",
    # Images
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "heic": "image/heic",
    "heif": "image/heif",
    "svg": "image/svg+xml",
    "ico": "image/x-icon",
    "jfif": "image/jpeg",
}


