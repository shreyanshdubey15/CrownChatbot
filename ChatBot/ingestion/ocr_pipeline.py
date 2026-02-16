"""
OCR Pipeline — Full Tesseract OCR for Scanned Documents
=========================================================
Wires up the Tesseract OCR engine for scanned PDFs and images.

Pipeline:
  1. PDF page → high-DPI image (PyMuPDF)
  2. Image preprocessing (deskew, denoise, threshold)
  3. Tesseract OCR → text
  4. Post-processing (cleanup, merge lines)
  5. Return Document objects with OCR metadata

Supports: PDF (scanned), PNG, JPG, TIFF, BMP
"""

import os
import re
from typing import List, Optional, Tuple
from langchain_core.documents import Document
from config.settings import settings


class OCRPipeline:
    """
    Production OCR pipeline using Tesseract + PyMuPDF.
    Automatically detects scanned PDFs and routes them through OCR.
    """

    def __init__(self):
        self._tesseract_available = False
        self._check_tesseract()

    def _check_tesseract(self):
        """Check if Tesseract is installed and accessible."""
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
            # Quick version check
            version = pytesseract.get_tesseract_version()
            print(f"[OCR] Tesseract {version} found at {settings.TESSERACT_CMD}")
            self._tesseract_available = True
        except Exception as e:
            print(f"[OCR] Tesseract not available: {e}")
            self._tesseract_available = False

    @property
    def is_available(self) -> bool:
        return self._tesseract_available

    def is_scanned_pdf(self, pdf_path: str) -> bool:
        """Detect if a PDF is scanned (image-based) vs native text."""
        try:
            import fitz
            pdf = fitz.open(pdf_path)
            total_text = ""
            for page_num in range(min(3, len(pdf))):
                page = pdf[page_num]
                total_text += page.get_text()
            pdf.close()
            return len(total_text.strip()) < 100
        except Exception:
            return False

    def ocr_pdf(
        self,
        pdf_path: str,
        dpi: int = 300,
        language: str = "eng",
        preprocess: bool = True,
    ) -> List[Document]:
        """
        Full OCR pipeline for a PDF.

        Args:
            pdf_path: Path to PDF file
            dpi: Resolution for rasterization (higher = better accuracy, slower)
            language: Tesseract language code
            preprocess: Enable image preprocessing

        Returns:
            List of Document objects (one per page)
        """
        if not self._tesseract_available:
            print("[OCR] Tesseract not available. Returning empty.")
            return []

        import fitz
        import pytesseract
        from PIL import Image
        import io

        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        base_name = os.path.basename(pdf_path)
        documents = []

        try:
            pdf = fitz.open(pdf_path)
            total_pages = len(pdf)
            print(f"[OCR] Processing {total_pages} pages from '{base_name}' at {dpi} DPI...")

            for page_num in range(total_pages):
                page = pdf[page_num]

                # Render page to image
                pix = page.get_pixmap(dpi=dpi)
                img_bytes = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_bytes))

                # Preprocess
                if preprocess:
                    image = self._preprocess_image(image)

                # OCR
                try:
                    text = pytesseract.image_to_string(
                        image,
                        lang=language,
                        config="--psm 6",  # Assume uniform block of text
                    )
                except Exception as e:
                    print(f"[OCR] Page {page_num + 1} failed: {e}")
                    text = ""

                # Post-process
                text = self._postprocess_text(text)

                if text.strip():
                    documents.append(Document(
                        page_content=text,
                        metadata={
                            "source": base_name,
                            "page": page_num + 1,
                            "extraction_method": "tesseract_ocr",
                            "ocr": True,
                            "dpi": dpi,
                            "language": language,
                        },
                    ))

            pdf.close()
            print(f"[OCR] Extracted text from {len(documents)}/{total_pages} pages")

        except Exception as e:
            print(f"[OCR] PDF OCR failed: {e}")

        return documents

    def ocr_image(
        self,
        image_path: str,
        language: str = "eng",
        preprocess: bool = True,
    ) -> Optional[str]:
        """
        OCR a single image file.

        Returns:
            Extracted text string
        """
        if not self._tesseract_available:
            return None

        import pytesseract
        from PIL import Image

        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

        try:
            image = Image.open(image_path)
            if preprocess:
                image = self._preprocess_image(image)

            text = pytesseract.image_to_string(
                image,
                lang=language,
                config="--psm 6",
            )
            return self._postprocess_text(text)

        except Exception as e:
            print(f"[OCR] Image OCR failed: {e}")
            return None

    def _preprocess_image(self, image):
        """
        Preprocess image for better OCR accuracy.
        - Convert to grayscale
        - Apply threshold
        - Denoise
        """
        try:
            from PIL import ImageFilter, ImageOps

            # Convert to grayscale
            if image.mode != "L":
                image = image.convert("L")

            # Auto-contrast
            image = ImageOps.autocontrast(image, cutoff=1)

            # Slight sharpen
            image = image.filter(ImageFilter.SHARPEN)

            return image
        except Exception:
            return image

    def _postprocess_text(self, text: str) -> str:
        """Clean up OCR output."""
        if not text:
            return ""

        # Fix common OCR errors
        text = text.replace("|", "I")  # Pipe → I (common OCR error)
        text = re.sub(r"\s{3,}", "  ", text)  # Reduce excessive spaces
        text = re.sub(r"\n{3,}", "\n\n", text)  # Reduce excessive newlines
        # Remove very short lines (likely noise)
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if len(stripped) > 1 or stripped in ("", " "):
                cleaned.append(line)
        return "\n".join(cleaned).strip()


# Module-level singleton
_ocr_pipeline: Optional[OCRPipeline] = None


def get_ocr_pipeline() -> OCRPipeline:
    global _ocr_pipeline
    if _ocr_pipeline is None:
        _ocr_pipeline = OCRPipeline()
    return _ocr_pipeline

