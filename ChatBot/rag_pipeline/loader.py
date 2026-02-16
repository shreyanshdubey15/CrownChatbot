from langchain_community.document_loaders import Docx2txtLoader, TextLoader, UnstructuredPDFLoader, UnstructuredWordDocumentLoader
from langchain_core.documents import Document
from pillow_heif import register_heif_opener
import os
import re
import sys
import pillow_heif


# Shim for older versions of unstructured that expect 'pi_heif'
sys.modules['pi_heif'] = pillow_heif

register_heif_opener()

# ── Supported file extensions ────────────────────────────────────
IMAGE_EXTENSIONS = (
    "jpg", "jpeg", "png",
    "webp", "heic", "heif", "svg", "ico", "jfif",
)

SPREADSHEET_EXTENSIONS = ("xlsx", "xls", "csv", "tsv")

ALL_LOADER_EXTENSIONS = (
    ("pdf",) + ("docx",) + ("doc",) + ("txt",) + ("rtf",) + ("md", "markdown")
    + SPREADSHEET_EXTENSIONS
    + IMAGE_EXTENSIONS
)


def clean_text(text):
    """
    Normalize whitespace while PRESERVING line breaks for the chunker.

    The chunker uses separators [\"\\n\\n\", \"\\n\", \". \", ...] so we MUST
    keep paragraph/line boundaries intact.  Only collapse spaces within lines
    and reduce runs of 3+ blank lines to 2.
    """
    # Normalize line endings (Windows \r\n → \n)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Clean each line: collapse multiple spaces within a line
    lines = text.split("\n")
    lines = [" ".join(line.split()) for line in lines]
    text = "\n".join(lines)
    # Reduce excessive blank lines (3+ → 2)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_pdf_smart_router(file_path, text_threshold=100):
    """
    Production-grade PDF loader with 3-tier cascading fallback strategy.
    
    Tier 1: Unstructured (intelligent semantic parsing)
    Tier 2: PyPDFLoader (fast text extraction)
    Tier 3: OCR (image-based PDFs, optional)
    
    Args:
        file_path: Path to PDF file
        text_threshold: Minimum text length to consider extraction successful (default: 100 chars)
    
    Returns:
        List of Document objects with metadata tracking extraction method
    """
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    base_name = os.path.basename(file_path)
    
    # ============================================
    # TIER 1: Unstructured (Intelligent Parsing)
    # ============================================
    print(f"[TIER 1] Attempting Unstructured extraction for '{base_name}'...")
    
    try:
        strategy = "hi_res" if file_size_mb > 1.0 else "fast"
        loader = UnstructuredPDFLoader(
            file_path,
            strategy=strategy,
            mode="elements",
            include_metadata=True
        )
        elements = loader.load()
        
        if elements:
            print(f"[TIER 1] SUCCESS! Extracted {len(elements)} elements using Unstructured")
            final_docs = []
            for el in elements:
                content = el.page_content.strip()
                if not content:
                    continue
                
                page_num = el.metadata.get("page_number", 1)
                new_doc = Document(
                    page_content=content,
                    metadata={
                        "source": base_name,
                        "page": page_num,
                        "element_type": el.metadata.get("category"),
                        "extraction_method": "unstructured",
                        "strategy": strategy
                    }
                )
                final_docs.append(new_doc)
            
            if final_docs:
                return final_docs
        
        print(f"[TIER 1] WARNING: Unstructured returned empty results, falling back to Tier 2...")
    
    except Exception as e:
        print(f"[TIER 1] WARNING: Unstructured failed: {str(e)[:100]}")
        print(f"         Falling back to Tier 2...")
    
    # ============================================
    # TIER 2: PyPDFLoader (Fast Text Extraction)
    # ============================================
    print(f"[TIER 2] Attempting PyPDFLoader extraction...")
    
    try:
        from langchain_community.document_loaders import PyPDFLoader
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        
        # Calculate total text length
        total_text = "".join([doc.page_content for doc in docs])
        text_length = len(total_text.strip())
        
        if text_length >= text_threshold:
            print(f"[TIER 2] SUCCESS! Extracted {text_length} chars using PyPDFLoader")
            
            # Standardize metadata
            for doc in docs:
                doc.metadata["source"] = base_name
                doc.metadata["extraction_method"] = "pypdf"
                doc.metadata["text_length"] = text_length
            
            return docs
        
        print(f"[TIER 2] WARNING: Text too short ({text_length} chars < {text_threshold} threshold)")
        print(f"         This might be an image-based PDF, falling back to Tier 3...")
    
    except Exception as e:
        print(f"[TIER 2] WARNING: PyPDFLoader failed: {str(e)[:100]}")
        print(f"         Falling back to Tier 3...")
    
    # ============================================
    # TIER 3: OCR Fallback (Image-based PDFs)
    # ============================================
    print(f"[TIER 3] Attempting OCR extraction (requires Tesseract)...")
    
    try:
        # Configure Tesseract path for Windows
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        except ImportError:
            pass  # pytesseract not installed, will fail gracefully below
        
        loader = UnstructuredPDFLoader(
            file_path,
            strategy="ocr_only",
            mode="single"
        )
        docs = loader.load()
        
        if docs and docs[0].page_content.strip():
            print(f"[TIER 3] SUCCESS! Extracted text using OCR")
            
            for doc in docs:
                doc.metadata["source"] = base_name
                doc.metadata["extraction_method"] = "ocr"
                doc.metadata["ocr"] = True
            
            return docs
        
        print(f"[TIER 3] FAILED: OCR returned empty results")
    
    except Exception as e:
        print(f"[TIER 3] FAILED: OCR failed: {str(e)[:100]}")
        if "poppler" in str(e).lower():
            print(f"         HINT: Install Poppler for PDF-to-image conversion")
            print(f"               Windows: choco install poppler")
        elif "tesseract" in str(e).lower():
            print(f"         HINT: Install Tesseract OCR for image-based PDF support")
            print(f"               Windows: choco install tesseract")
    
    # ============================================
    # ALL TIERS FAILED
    # ============================================
    print(f"[ALL TIERS FAILED] Could not extract content from '{base_name}'")
    print(f"                   Returning empty document list")
    
    return []


def _extract_text_from_doc_ole(file_path):
    """
    Pure Python extraction of text from legacy .doc (Word 97-2003) binary format.
    Parses the OLE2 compound document, reads the FIB, piece table, and assembles text.
    No external tools (LibreOffice, MS Word, antiword) required.

    Returns:
        Extracted text as a string, or empty string on failure.
    """
    import struct
    import olefile

    ole = olefile.OleFileIO(file_path)

    # Read the WordDocument stream (contains the FIB and text)
    word_doc = ole.openstream('WordDocument').read()

    # --- Parse FIB (File Information Block) ---
    # Offset 0x000A: flags word
    flags = struct.unpack_from('<H', word_doc, 0x000A)[0]
    f_which_tbl = (flags >> 9) & 1  # bit 9 = which table stream (0Table or 1Table)

    table_name = '1Table' if f_which_tbl else '0Table'
    if not ole.exists(table_name):
        ole.close()
        return ""

    table_data = ole.openstream(table_name).read()

    # FIB offsets for CLX (Complex file format data)
    # Word97+: fcClx at 0x01A2, lcbClx at 0x01A6
    fc_clx = struct.unpack_from('<I', word_doc, 0x01A2)[0]
    lcb_clx = struct.unpack_from('<I', word_doc, 0x01A6)[0]

    if lcb_clx == 0:
        ole.close()
        return ""

    # Read CLX structure from the Table stream
    clx = table_data[fc_clx:fc_clx + lcb_clx]

    # Parse CLX to find the PlcPcd (Piece Table)
    pos = 0
    text_parts = []

    while pos < len(clx):
        clx_type = clx[pos]

        if clx_type == 1:
            # PrcData: skip over it
            cb_grpprl = struct.unpack_from('<H', clx, pos + 1)[0]
            pos += 3 + cb_grpprl

        elif clx_type == 2:
            # PlcPcd: the piece table we need
            cb = struct.unpack_from('<I', clx, pos + 1)[0]
            piece_table = clx[pos + 5:pos + 5 + cb]

            # PlcPcd layout: (n+1) CPs (4 bytes each), then n PCDs (8 bytes each)
            # (n+1)*4 + n*8 = cb  =>  n = (cb - 4) // 12
            n = (cb - 4) // 12

            # Read character positions (CPs)
            cps = []
            for i in range(n + 1):
                cp = struct.unpack_from('<I', piece_table, i * 4)[0]
                cps.append(cp)

            # Read Piece Descriptors (PCDs)
            pcd_offset = (n + 1) * 4
            for i in range(n):
                pcd = piece_table[pcd_offset + i * 8:pcd_offset + (i + 1) * 8]

                # PCD: 2 bytes descriptor, 4 bytes fc, 2 bytes prm
                fc_value = struct.unpack_from('<I', pcd, 2)[0]

                # Bit 30 (0x40000000): fCompressed flag
                is_compressed = bool(fc_value & 0x40000000)
                fc_value = fc_value & 0x3FFFFFFF  # Clear bit 30 and 31

                char_count = cps[i + 1] - cps[i]

                if is_compressed:
                    # Compressed (ANSI/cp1252): fc is byte offset / 2
                    byte_offset = fc_value // 2
                    text_bytes = word_doc[byte_offset:byte_offset + char_count]
                    text_parts.append(text_bytes.decode('cp1252', errors='ignore'))
                else:
                    # Uncompressed (UTF-16LE): fc is byte offset
                    byte_count = char_count * 2
                    text_bytes = word_doc[fc_value:fc_value + byte_count]
                    text_parts.append(text_bytes.decode('utf-16-le', errors='ignore'))

            break  # Only one PlcPcd in CLX
        else:
            break  # Unknown type, stop

    ole.close()

    # Join all pieces and clean control characters
    raw_text = ''.join(text_parts)

    # Replace Word special characters
    raw_text = raw_text.replace('\r', '\n')       # Paragraph marks
    raw_text = raw_text.replace('\x07', '\t')      # Cell marks -> tab
    raw_text = raw_text.replace('\x0b', '\n')      # Vertical tab -> newline
    raw_text = raw_text.replace('\x0c', '\n')      # Page break -> newline
    raw_text = raw_text.replace('\x01', '')         # Field begin
    raw_text = raw_text.replace('\x13', '')         # Field separator
    raw_text = raw_text.replace('\x14', '')         # Field separator
    raw_text = raw_text.replace('\x15', '')         # Field end
    raw_text = raw_text.replace('\x08', '')         # Drawing anchor

    # Remove remaining non-printable chars (except whitespace)
    raw_text = ''.join(c for c in raw_text if c.isprintable() or c in '\n\r\t ')

    return raw_text.strip()


def _convert_doc_with_word(file_path):
    """
    Convert a legacy .doc file to .docx using Microsoft Word via win32com (Windows only).
    Returns the path to the converted .docx file, or None if conversion fails.
    """
    import tempfile
    word = None
    try:
        import win32com.client
        import pythoncom

        pythoncom.CoInitialize()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = False

        abs_path = os.path.abspath(file_path)
        tmp_dir = tempfile.mkdtemp()
        docx_name = os.path.splitext(os.path.basename(file_path))[0] + ".docx"
        docx_path = os.path.join(tmp_dir, docx_name)

        doc = word.Documents.Open(abs_path)
        doc.SaveAs2(os.path.abspath(docx_path), FileFormat=16)  # 16 = wdFormatXMLDocument (.docx)
        doc.Close()
        word.Quit()
        pythoncom.CoUninitialize()

        return docx_path
    except ImportError:
        return None
    except Exception as e:
        try:
            if word:
                word.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        raise e


def load_doc_smart_router(file_path):
    """
    Production-grade .doc loader with 5-tier cascading fallback strategy.

    Tier 1: UnstructuredWordDocumentLoader (semantic parsing, needs LibreOffice)
    Tier 2: Pure Python OLE binary parser (no external tools needed)
    Tier 3: MS Word via win32com (Windows only, needs MS Word installed)
    Tier 4: LibreOffice CLI conversion to .docx
    Tier 5: Direct docx2txt (catches misnamed .docx files)

    Args:
        file_path: Path to .doc file

    Returns:
        List of Document objects with metadata tracking extraction method
    """
    base_name = os.path.basename(file_path)

    # ============================================
    # TIER 1: UnstructuredWordDocumentLoader
    # ============================================
    print(f"[DOC TIER 1] Attempting UnstructuredWordDocumentLoader for '{base_name}'...")

    try:
        loader = UnstructuredWordDocumentLoader(file_path, mode="single")
        docs = loader.load()

        if docs and docs[0].page_content.strip():
            print(f"[DOC TIER 1] SUCCESS! Extracted {len(docs)} document(s) using Unstructured")
            for doc in docs:
                doc.page_content = clean_text(doc.page_content)
                doc.metadata["source"] = base_name
                doc.metadata["extraction_method"] = "unstructured_word"
                doc.metadata["ocr"] = False
            return docs

        print(f"[DOC TIER 1] WARNING: Returned empty content, falling back...")

    except Exception as e:
        print(f"[DOC TIER 1] WARNING: Failed: {str(e)[:150]}")
        print(f"             Falling back to Tier 2...")

    # ============================================
    # TIER 2: Pure Python OLE Binary Parser
    # ============================================
    print(f"[DOC TIER 2] Attempting pure Python OLE extraction for '{base_name}'...")

    try:
        extracted = _extract_text_from_doc_ole(file_path)

        if extracted and len(extracted.strip()) > 50:
            print(f"[DOC TIER 2] SUCCESS! Extracted {len(extracted)} chars via OLE binary parser")
            doc = Document(
                page_content=clean_text(extracted),
                metadata={
                    "source": base_name,
                    "page": 1,
                    "extraction_method": "ole_binary_parser",
                    "ocr": False,
                }
            )
            return [doc]

        print(f"[DOC TIER 2] WARNING: OLE extraction returned insufficient text ({len(extracted) if extracted else 0} chars)")

    except Exception as e:
        print(f"[DOC TIER 2] WARNING: Failed: {str(e)[:150]}")
        print(f"             Falling back to Tier 3...")

    # ============================================
    # TIER 3: MS Word via win32com (Windows only)
    # ============================================
    print(f"[DOC TIER 3] Attempting MS Word conversion via win32com...")

    try:
        converted_path = _convert_doc_with_word(file_path)

        if converted_path and os.path.exists(converted_path):
            loader = Docx2txtLoader(converted_path)
            docs = loader.load()

            # Cleanup temp file
            try:
                os.remove(converted_path)
                os.rmdir(os.path.dirname(converted_path))
            except Exception:
                pass

            if docs and docs[0].page_content.strip():
                print(f"[DOC TIER 3] SUCCESS! Converted .doc -> .docx via MS Word")
                for doc in docs:
                    doc.page_content = clean_text(doc.page_content)
                    doc.metadata["source"] = base_name
                    doc.metadata["extraction_method"] = "win32com_word"
                    doc.metadata["ocr"] = False
                return docs

            print(f"[DOC TIER 3] WARNING: Conversion produced empty content")
        else:
            print(f"[DOC TIER 3] SKIPPED: MS Word not installed")

    except Exception as e:
        print(f"[DOC TIER 3] WARNING: Failed: {str(e)[:150]}")
        print(f"             Falling back to Tier 4...")

    # ============================================
    # TIER 4: LibreOffice conversion to .docx
    # ============================================
    print(f"[DOC TIER 4] Attempting LibreOffice conversion to .docx...")

    try:
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                ["soffice", "--headless", "--convert-to", "docx", "--outdir", tmpdir, file_path],
                capture_output=True, text=True, timeout=60
            )

            docx_name = os.path.splitext(base_name)[0] + ".docx"
            converted_path = os.path.join(tmpdir, docx_name)

            if os.path.exists(converted_path):
                loader = Docx2txtLoader(converted_path)
                docs = loader.load()
                if docs and docs[0].page_content.strip():
                    print(f"[DOC TIER 4] SUCCESS! Converted .doc -> .docx via LibreOffice")
                    for doc in docs:
                        doc.page_content = clean_text(doc.page_content)
                        doc.metadata["source"] = base_name
                        doc.metadata["extraction_method"] = "libreoffice_conversion"
                        doc.metadata["ocr"] = False
                    return docs

            print(f"[DOC TIER 4] WARNING: Conversion produced empty or no file")

    except FileNotFoundError:
        print(f"[DOC TIER 4] SKIPPED: LibreOffice not installed")
    except subprocess.TimeoutExpired:
        print(f"[DOC TIER 4] FAILED: LibreOffice conversion timed out")
    except Exception as e:
        print(f"[DOC TIER 4] WARNING: Failed: {str(e)[:150]}")

    # ============================================
    # TIER 5: Direct docx2txt (misnamed .docx)
    # ============================================
    print(f"[DOC TIER 5] Attempting direct docx2txt extraction (for misnamed .docx files)...")

    try:
        loader = Docx2txtLoader(file_path)
        docs = loader.load()

        if docs and docs[0].page_content.strip():
            print(f"[DOC TIER 5] SUCCESS! File was actually a .docx internally")
            for doc in docs:
                doc.page_content = clean_text(doc.page_content)
                doc.metadata["source"] = base_name
                doc.metadata["extraction_method"] = "docx2txt_direct"
                doc.metadata["ocr"] = False
            return docs

        print(f"[DOC TIER 5] FAILED: docx2txt returned empty results")

    except Exception as e:
        print(f"[DOC TIER 5] FAILED: {str(e)[:100]}")

    # ============================================
    # ALL TIERS FAILED
    # ============================================
    print(f"[DOC ALL TIERS FAILED] Could not extract content from '{base_name}'")
    print(f"                       Returning empty document list")

    return []


def load_image_smart_router(file_path):
    """
    Production-grade image loader with 3-tier cascading fallback strategy.

    Tier 1: OCR via Tesseract (pytesseract + Pillow)
    Tier 2: LLM-based image description (via OCR pipeline)
    Tier 3: Metadata-only fallback (image dimensions, format, filename)

    Supports: JPG, JPEG, PNG, GIF, BMP, TIFF, TIF, WEBP, HEIC, HEIF, SVG, ICO, JFIF

    Args:
        file_path: Path to image file

    Returns:
        List of Document objects with metadata tracking extraction method
    """
    base_name = os.path.basename(file_path)

    # ============================================
    # TIER 1: OCR via Tesseract (pytesseract)
    # ============================================
    print(f"[IMG TIER 1] Attempting OCR extraction for '{base_name}'...")

    try:
        from ingestion.ocr_pipeline import get_ocr_pipeline

        ocr = get_ocr_pipeline()
        if ocr.is_available:
            text = ocr.ocr_image(file_path)
            if text and len(text.strip()) > 10:
                print(f"[IMG TIER 1] SUCCESS! Extracted {len(text)} chars via Tesseract OCR")
                doc = Document(
                    page_content=clean_text(text),
                    metadata={
                        "source": base_name,
                        "page": 1,
                        "extraction_method": "tesseract_ocr",
                        "ocr": True,
                        "element_type": "image_text",
                    },
                )
                return [doc]
            print(f"[IMG TIER 1] WARNING: OCR returned insufficient text ({len(text.strip()) if text else 0} chars)")
        else:
            print(f"[IMG TIER 1] SKIPPED: Tesseract not available")
    except Exception as e:
        print(f"[IMG TIER 1] WARNING: OCR failed: {str(e)[:150]}")

    # ============================================
    # TIER 2: Direct pytesseract (no OCR pipeline)
    # ============================================
    print(f"[IMG TIER 2] Attempting direct pytesseract extraction...")

    try:
        import pytesseract
        from PIL import Image
        from config.settings import settings

        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        image = Image.open(file_path)

        # Convert to RGB if necessary (handles RGBA, P, L modes)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        text = pytesseract.image_to_string(image, config="--psm 6")

        if text and len(text.strip()) > 10:
            print(f"[IMG TIER 2] SUCCESS! Extracted {len(text.strip())} chars via direct pytesseract")
            doc = Document(
                page_content=clean_text(text),
                metadata={
                    "source": base_name,
                    "page": 1,
                    "extraction_method": "pytesseract_direct",
                    "ocr": True,
                    "element_type": "image_text",
                },
            )
            return [doc]
        print(f"[IMG TIER 2] WARNING: Insufficient text ({len(text.strip()) if text else 0} chars)")
    except ImportError:
        print(f"[IMG TIER 2] SKIPPED: pytesseract not installed")
    except Exception as e:
        print(f"[IMG TIER 2] WARNING: Failed: {str(e)[:150]}")

    # ============================================
    # TIER 3: Metadata-only fallback (NO useful text)
    # ============================================
    # If OCR failed, we return an empty list so this image
    # does NOT pollute the vector DB with non-content data.
    # The file is still saved on disk and tracked in the registry.
    print(f"[IMG TIER 3] No text extracted from '{base_name}' (OCR unavailable)")
    print(f"             HINT: Install Tesseract OCR for image text extraction")
    print(f"             Image will be saved but NOT indexed in vector DB")

    # ============================================
    # ALL TIERS FAILED
    # ============================================
    print(f"[IMG ALL TIERS FAILED] Could not process image '{base_name}'")
    return []


def _read_text_with_fallback(file_path: str) -> str:
    """Read a text file trying multiple encodings."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "ascii"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # Binary fallback
    with open(file_path, "rb") as f:
        return f.read().decode("utf-8", errors="replace")


def load_rtf(file_path: str) -> list:
    """Extract text from RTF (Rich Text Format) files."""
    base_name = os.path.basename(file_path)
    print(f"[RTF] Loading '{base_name}'...")
    try:
        # Try striprtf library first
        try:
            from striprtf.striprtf import rtf_to_text
            raw = _read_text_with_fallback(file_path)
            text = rtf_to_text(raw)
        except ImportError:
            # Fallback: regex-based RTF stripping
            import re
            raw = _read_text_with_fallback(file_path)
            # Remove RTF control words and groups
            text = re.sub(r"\\[a-z]+\d*\s?", " ", raw)
            text = re.sub(r"[{}]", "", text)
            text = re.sub(r"\\\'[0-9a-fA-F]{2}", " ", text)  # hex chars
            text = "\n".join(line.strip() for line in text.split("\n") if line.strip())

        if not text.strip():
            return []

        doc = Document(
            page_content=clean_text(text),
            metadata={
                "source": base_name,
                "page": 1,
                "extraction_method": "rtf_loader",
                "element_type": "document_text",
            },
        )
        print(f"[RTF] Loaded {len(text)} chars")
        return [doc]
    except Exception as e:
        print(f"[RTF] Loading failed: {e}")
        return []


def load_single_doc(file_path):
    """
    Document loader — routes supported files to their best extractor.

    Supported formats:
      Documents : .pdf, .docx, .doc, .rtf
      Plain text: .txt, .md, .markdown
      Sheets    : .xlsx, .xls, .csv, .tsv
      Images    : .jpg, .jpeg, .png, .webp, .heic, .heif, .svg, .ico, .jfif

    Returns:
        List of Document objects with metadata
    """
    if not os.path.isfile(file_path):
        return []

    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    base_name = os.path.basename(file_path)

    # ── Documents ─────────────────────────────────────────────
    if ext == "docx":
        loader = Docx2txtLoader(file_path)
        docs = loader.load()
        for doc in docs:
            doc.metadata.setdefault("page", 1)
            doc.metadata["extraction_method"] = "docx2txt"
    elif ext == "doc":
        return load_doc_smart_router(file_path)
    elif ext == "pdf":
        return load_pdf_smart_router(file_path)
    elif ext == "rtf":
        return load_rtf(file_path)

    # ── Plain text (with encoding fallback) ───────────────────
    elif ext in ("txt", "md", "markdown"):
        try:
            text = _read_text_with_fallback(file_path)
            if not text.strip():
                print(f"[LOADER] Empty file: '{base_name}'")
                return []
            docs = [Document(
                page_content=text,
                metadata={
                    "page": 1,
                    "extraction_method": f"{ext}_loader",
                },
            )]
        except Exception as e:
            print(f"[LOADER] Text loading failed for '{base_name}': {e}")
            return []

    # ── Spreadsheets ──────────────────────────────────────────
    elif ext in SPREADSHEET_EXTENSIONS:
        from ingestion.excel_loader import get_excel_loader
        loader = get_excel_loader()
        docs = loader.load(file_path)
        if docs:
            return docs
        return []

    # ── Images ────────────────────────────────────────────────
    elif ext in IMAGE_EXTENSIONS:
        return load_image_smart_router(file_path)

    else:
        print(f"[LOADER] Unsupported file type: .{ext} for '{base_name}'")
        return []

    # ── Clean up for simple loaders (docx, txt, md) ───────────
    for doc in docs:
        doc.page_content = clean_text(doc.page_content)
        doc.metadata["source"] = base_name
        doc.metadata["ocr"] = False

    total_chars = sum(len(d.page_content) for d in docs)
    method = docs[0].metadata.get("extraction_method", "unknown") if docs else "unknown"
    print(f"[LOADER] Loaded '{base_name}' - {len(docs)} doc(s), {total_chars} chars via {method}")

    return docs


def load_documents(data_path="data"):
    """Load all supported files from a directory."""
    documents = []

    if not os.path.isdir(data_path):
        print(f"[LOADER] Directory not found: {data_path}")
        return documents

    for file in os.listdir(data_path):
        file_path = os.path.join(data_path, file)
        # Skip directories, hidden files, and system files
        if not os.path.isfile(file_path):
            continue
        if file.startswith(".") or file.startswith("~"):
            continue
        try:
            docs = load_single_doc(file_path)
            documents.extend(docs)
        except Exception as e:
            print(f"[LOADER] Error loading '{file}': {e}")

    return documents


# Alias for user-friendly testing
load_pdf = load_single_doc

if __name__ == "__main__":
    print("=" * 60)
    print("SMART LOADER ROUTER - TEST SUITE")
    print("=" * 60)
    
    pdf_path = "data/uploads/dialphone_features.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"\n[ERROR] File not found at {pdf_path}")
        print("        Please ensure the PDF exists before running tests.")
    else:
        print(f"\n[INFO] Testing file: {pdf_path}")
        print(f"       Size: {os.path.getsize(pdf_path)} bytes\n")
        
        # Run the smart loader router
        docs = load_pdf(pdf_path)
        
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        
        if docs:
            print(f"\n[SUCCESS] Extracted {len(docs)} document(s)\n")
            
            # Show details for first 3 documents
            for i, doc in enumerate(docs[:3]):
                print(f"--- Document {i+1} ---")
                print(f"Extraction Method: {doc.metadata.get('extraction_method', 'unknown')}")
                print(f"Source: {doc.metadata.get('source', 'unknown')}")
                print(f"Page: {doc.metadata.get('page', 'unknown')}")
                
                if 'element_type' in doc.metadata:
                    print(f"Element Type: {doc.metadata['element_type']}")
                if 'text_length' in doc.metadata:
                    print(f"Total Text Length: {doc.metadata['text_length']}")
                
                content_preview = doc.page_content[:200].replace('\n', ' ')
                print(f"Content Preview: {content_preview}...")
                print()
            
            if len(docs) > 3:
                print(f"... and {len(docs) - 3} more document(s)\n")
        else:
            print("\n[FAILED] No documents extracted")
            print("         All 3 tiers failed. Check logs above for details.\n")

