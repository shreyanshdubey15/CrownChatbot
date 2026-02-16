"""
Extraction Routes — OCR & Handwriting
=======================================
/ocr-extract, /handwriting-recognize
"""

import os
import uuid
import shutil

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from config.constants import AUTOFILL_TEMP_DIR
from utils.form_filler import safe_remove

router = APIRouter(tags=["Extraction"])


@router.post("/ocr-extract", summary="Run OCR on a scanned document")
async def ocr_extract(
    file: UploadFile = File(...),
    language: str = Form("eng"),
    dpi: int = Form(300),
):
    """Run Tesseract OCR on a scanned PDF or image. Returns extracted text per page."""
    from ingestion.ocr_pipeline import get_ocr_pipeline

    ocr = get_ocr_pipeline()
    if not ocr.is_available:
        raise HTTPException(status_code=503, detail="Tesseract OCR not installed or not found.")

    tmp_path = os.path.join(AUTOFILL_TEMP_DIR, f"ocr_{uuid.uuid4()}.{file.filename.rsplit('.', 1)[-1]}")
    try:
        with open(tmp_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext == "pdf":
            docs = ocr.ocr_pdf(tmp_path, dpi=dpi, language=language)
            pages = [{"page": d.metadata.get("page", 1), "text": d.page_content} for d in docs]
        else:
            text = ocr.ocr_image(tmp_path, language=language)
            pages = [{"page": 1, "text": text or ""}]

        return {
            "filename": file.filename,
            "pages": pages,
            "total_pages": len(pages),
            "total_chars": sum(len(p["text"]) for p in pages),
        }
    finally:
        safe_remove(tmp_path)


@router.post("/handwriting-recognize", summary="Recognize handwritten text from an image or PDF page")
async def handwriting_recognize(
    file: UploadFile = File(...),
    page: int = Form(0),
):
    """Run handwriting recognition (TrOCR) on an uploaded image or PDF page."""
    from ingestion.handwriting_engine import get_handwriting_engine

    engine = get_handwriting_engine()

    tmp_path = os.path.join(AUTOFILL_TEMP_DIR, f"hw_{uuid.uuid4()}.{file.filename.rsplit('.', 1)[-1]}")
    try:
        with open(tmp_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext == "pdf":
            text = engine.recognize_from_pdf_page(tmp_path, page_number=page)
        else:
            from PIL import Image
            image = Image.open(tmp_path).convert("RGB")
            text = engine.recognize_handwriting(image)

        return {
            "filename": file.filename,
            "page": page,
            "text": text or "",
            "method": "trocr" if engine.is_available else "tesseract_fallback",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Handwriting recognition failed: {e}")
    finally:
        safe_remove(tmp_path)


