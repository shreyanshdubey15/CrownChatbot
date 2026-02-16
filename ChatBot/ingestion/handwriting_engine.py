"""
Handwriting Recognition Engine (ICR)
======================================
For scanned forms with handwritten entries.

Uses TrOCR (Transformer-based OCR) for handwriting recognition.
Falls back to Tesseract with handwriting-optimized config.

Pipeline:
  1. Detect handwritten regions (contrast with printed text)
  2. Crop handwritten regions
  3. TrOCR model → text
  4. Merge with printed text OCR results
"""

import os
from typing import Optional, List, Dict, Any
from config.settings import settings


class HandwritingEngine:
    """
    Handwriting recognition using TrOCR or Tesseract fallback.
    Lazy-loads models to avoid memory pressure.
    """

    def __init__(self):
        self._trocr_model = None
        self._trocr_processor = None
        self._device = None
        self._available = None

    def _get_device(self):
        if self._device is None:
            try:
                import torch
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                self._device = "cpu"
        return self._device

    def _load_trocr(self):
        """Lazy-load TrOCR model for handwriting recognition."""
        if self._trocr_model is not None:
            return True

        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel

            model_name = "microsoft/trocr-base-handwritten"
            print(f"[HANDWRITING] Loading TrOCR from {model_name}...")

            self._trocr_processor = TrOCRProcessor.from_pretrained(model_name)
            self._trocr_model = VisionEncoderDecoderModel.from_pretrained(model_name)
            self._trocr_model.to(self._get_device())
            self._trocr_model.eval()

            print("[HANDWRITING] TrOCR loaded successfully.")
            self._available = True
            return True

        except Exception as e:
            print(f"[HANDWRITING] TrOCR not available: {e}")
            self._available = False
            return False

    @property
    def is_available(self) -> bool:
        if self._available is None:
            self._load_trocr()
        return self._available or False

    def recognize_handwriting(
        self,
        image,
        max_length: int = 128,
    ) -> Optional[str]:
        """
        Recognize handwritten text from a PIL Image.

        Args:
            image: PIL Image containing handwritten text
            max_length: Maximum output token length

        Returns:
            Recognized text string
        """
        if not self._load_trocr():
            return self._fallback_tesseract(image)

        try:
            import torch

            # Ensure RGB
            if image.mode != "RGB":
                image = image.convert("RGB")

            pixel_values = self._trocr_processor(
                images=image,
                return_tensors="pt",
            ).pixel_values.to(self._get_device())

            with torch.no_grad():
                generated_ids = self._trocr_model.generate(
                    pixel_values,
                    max_length=max_length,
                )

            text = self._trocr_processor.batch_decode(
                generated_ids,
                skip_special_tokens=True,
            )[0]

            return text.strip()

        except Exception as e:
            print(f"[HANDWRITING] TrOCR recognition failed: {e}")
            return self._fallback_tesseract(image)

    def recognize_regions(
        self,
        image,
        regions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Recognize handwritten text in multiple image regions.

        Args:
            image: Full PIL Image
            regions: List of {x0, y0, x1, y1} bounding boxes

        Returns:
            List of {bbox: ..., text: ..., confidence: ...}
        """
        results = []

        for region in regions:
            x0 = int(region.get("x0", 0))
            y0 = int(region.get("y0", 0))
            x1 = int(region.get("x1", image.width))
            y1 = int(region.get("y1", image.height))

            cropped = image.crop((x0, y0, x1, y1))
            text = self.recognize_handwriting(cropped)

            results.append({
                "bbox": [x0, y0, x1, y1],
                "text": text or "",
                "confidence": 0.7 if text else 0.0,
                "method": "trocr" if self._available else "tesseract",
            })

        return results

    def recognize_from_pdf_page(
        self,
        pdf_path: str,
        page_number: int = 0,
        dpi: int = 300,
    ) -> Optional[str]:
        """
        Extract handwritten text from a specific PDF page.
        """
        try:
            import fitz
            from PIL import Image
            import io

            pdf = fitz.open(pdf_path)
            if page_number >= len(pdf):
                pdf.close()
                return None

            page = pdf[page_number]
            pix = page.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            pdf.close()

            return self.recognize_handwriting(image)

        except Exception as e:
            print(f"[HANDWRITING] PDF page recognition failed: {e}")
            return None

    def _fallback_tesseract(self, image) -> Optional[str]:
        """Fallback to Tesseract with handwriting-friendly config."""
        try:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

            # PSM 7 = single text line, PSM 13 = raw line
            text = pytesseract.image_to_string(
                image,
                lang="eng",
                config="--psm 7 --oem 3",
            )
            return text.strip() if text else None

        except Exception as e:
            print(f"[HANDWRITING] Tesseract fallback failed: {e}")
            return None


# Module-level singleton
_handwriting_engine: Optional[HandwritingEngine] = None


def get_handwriting_engine() -> HandwritingEngine:
    global _handwriting_engine
    if _handwriting_engine is None:
        _handwriting_engine = HandwritingEngine()
    return _handwriting_engine

