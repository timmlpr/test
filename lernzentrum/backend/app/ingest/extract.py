"""Text extraction for PDF, Word, PowerPoint, images (OCR) and plain text.

OCR order: embedded PDF text → Tesseract (deu) → Gemini vision (handwriting, GoodNotes ink) when a key exists.
Returns page texts so chunks keep their page/slide number.
"""
from __future__ import annotations

import io
import logging
import shutil
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import User
from ..providers import registry

log = logging.getLogger("lz.extract")

AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".opus", ".webm", ".mp4", ".caf", ".flac"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff"}


@dataclass
class Extracted:
    pages: list[str]
    method: str
    notes: list[str] = field(default_factory=list)
    handwriting: bool = False


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _ocr_image(db: Session | None, user: User | None, img_bytes: bytes, mime: str = "image/png") -> tuple[str, str]:
    text = ""
    if tesseract_available():
        try:
            import pytesseract
            from PIL import Image

            text = pytesseract.image_to_string(Image.open(io.BytesIO(img_bytes)), lang="deu+eng")
        except Exception as exc:  # noqa: BLE001
            log.info("tesseract failed: %s", exc)
    if len(text.strip()) >= 40:
        return text, "tesseract"
    if db is not None and user is not None:
        try:
            v = registry.vision_ocr(db, user, img_bytes, mime)
            if v:
                return v, "gemini-vision"
        except Exception as exc:  # noqa: BLE001 - quota/provider issues → keep tesseract result
            log.info("vision OCR failed: %s", exc)
    return text, "tesseract" if text else "none"


def _pdf(data: bytes, db: Session | None, user: User | None) -> Extracted:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(p.extract_text() or "") for p in reader.pages]
    empty = [i for i, t in enumerate(pages) if len(t.strip()) < 25]
    method, notes, hw = "pdf-text", [], False
    if empty:
        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(data)
            for i in empty[:60]:
                img = pdf[i].render(scale=2).to_pil()
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                txt, m = _ocr_image(db, user, buf.getvalue())
                pages[i] = txt
                method = f"pdf-text+{m}"
                hw = hw or m == "gemini-vision"
            if len(empty) > 60:
                notes.append(f"{len(empty) - 60} Seiten ohne Text nicht per OCR verarbeitet (Limit).")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"OCR nicht möglich: {exc}")
    if empty and not tesseract_available() and not (db and user and registry.llm_for(db, user)):
        notes.append("Handschrift/Scan erkannt – für OCR Gemini-Key hinterlegen oder Docker-Image (mit Tesseract) "
                     "verwenden.")
    return Extracted(pages, method, notes, hw)


def _docx(data: bytes) -> Extracted:
    import docx

    d = docx.Document(io.BytesIO(data))
    paras = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            paras.append(" | ".join(c.text for c in row.cells))
    text = "\n".join(paras)
    pages = [text[i:i + 3000] for i in range(0, len(text), 3000)] or [""]
    return Extracted(pages, "docx")


def _pptx(data: bytes) -> Extracted:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    pages = []
    for slide in prs.slides:
        parts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
        if slide.has_notes_slide:
            parts.append("Notizen: " + slide.notes_slide.notes_text_frame.text)
        pages.append("\n".join(parts))
    return Extracted(pages, "pptx")


def extract(data: bytes, filename: str, mime: str, db: Session | None = None, user: User | None = None) -> Extracted:
    name = filename.lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext == ".pdf" or mime == "application/pdf":
        return _pdf(data, db, user)
    if ext == ".docx":
        return _docx(data)
    if ext == ".pptx":
        return _pptx(data)
    if ext in IMAGE_EXT or mime.startswith("image/"):
        if ext in (".heic", ".heif"):
            return Extracted([""], "none", ["HEIC wird nicht direkt unterstützt – bitte als JPG teilen."])
        txt, m = _ocr_image(db, user, data, mime or "image/jpeg")
        return Extracted([txt], m, [] if txt.strip() else ["Kein Text erkannt."], m == "gemini-vision")
    if ext in (".txt", ".md", ".csv") or mime.startswith("text/"):
        text = data.decode("utf-8", errors="replace")
        return Extracted([text[i:i + 3000] for i in range(0, len(text), 3000)] or [""], "text")
    if ext in (".doc", ".ppt"):
        return Extracted([""], "none", ["Altes Office-Format – bitte als .docx/.pptx oder PDF exportieren."])
    return Extracted([""], "none", [f"Dateityp {ext or mime} wird nicht ausgelesen."])
