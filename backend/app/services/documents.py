"""This file handles document uploads and indexing in Aether AI. It accepts PDF, Word, text, and Markdown files, extracts their text, splits it into smaller chunks, stores the document in the database, and indexes the chunks for AI search (RAG)."""


# clean_text()	Removes unwanted characters and extra spaces while preserving paragraphs.
# extract_text()	Extracts readable text from PDF, DOCX, TXT, and Markdown files. uses clean_text()
# chunk_text()	Splits extracted text into smaller chunks of 800 characters, with 150 characters of overlap.
# upload_document()	Main upload function. Validates files, detects duplicates, saves the document, and starts indexing.
# index_document()	Indexes document chunks in the vector store and updates the database with indexing status.
import base64
import hashlib
import logging
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pymupdf
from docx import Document as WordDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import config
from app.core.memory import check_and_collect_garbage, log_stage_memory
from app.models.database import Document, new_id
from app.services import storage

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


def clean_text(text: str) -> str:
    """Remove nulls and repeated spaces while preserving paragraph boundaries."""
    text = text.replace("\x00", "").replace("\r\n", "\n")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def ocr_page_image(page) -> str:
    """Render a scanned PDF page to JPEG and transcribe using Gemini Vision.

    Tries models in fallback order and handles both plain-string and
    list-of-dicts response content (newer Gemini models return content blocks).
    """
    logger = logging.getLogger("aether.documents")
    try:
        pix = page.get_pixmap(dpi=150)
        jpeg_bytes = pix.tobytes("jpeg")
        del pix
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        del jpeg_bytes
    except Exception as exc:
        logger.warning("OCR: failed to render page to image: %s", exc)
        return ""

    from langchain_core.messages import HumanMessage
    from app.services.ai import create_llm

    prompt_msg = HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    "Transcribe all readable text from this scanned document page accurately. "
                    "Preserve original paragraph structure. "
                    "Return ONLY the transcribed text without conversational commentary or markdown code blocks."
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            },
        ]
    )

    # Try the configured model first, then known-good fallbacks
    fallback_models = [
        config.gemini_ocr_model,
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ]
    # Deduplicate while preserving order
    seen: set[str] = set()
    ocr_models = [m for m in fallback_models if not (m in seen or seen.add(m))]  # type: ignore[func-returns-value]

    for model_name in ocr_models:
        try:
            llm = create_llm(model_name)
            response = llm.invoke([prompt_msg])
            raw = getattr(response, "content", "") or ""
            # Gemini may return a list of content blocks instead of a plain string
            if isinstance(raw, list):
                text = " ".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in raw
                )
            else:
                text = raw
            text = clean_text(text)
            if text:
                if model_name != config.gemini_ocr_model:
                    logger.info("OCR succeeded with fallback model %s", model_name)
                return text
        except Exception as exc:
            logger.warning("OCR model %s failed: %s — trying next", model_name, exc)
            continue

    logger.error("OCR: all Gemini models exhausted; returning empty string for page")
    return ""


def extract_text(source: bytes | Path | str, extension: str) -> list[dict]: 
    """Extract page-aware PDF text, Word paragraphs/tables, or UTF-8 plain text.

    Supports both file paths (for low memory usage) and bytes (for in-memory sources).
    """
    max_chars = config.max_extracted_chars
    total_chars = 0
    segments = []

    try:
        if extension == ".pdf":
            pdf_context = (
                pymupdf.open(str(source))
                if isinstance(source, (str, Path))
                else pymupdf.open(stream=source, filetype="pdf")
            )
            with pdf_context as pdf:
                if pdf.is_encrypted:
                    raise ValueError("Password-protected PDFs are not supported.")
                for i, page in enumerate(pdf):
                    cleaned = clean_text(page.get_text())
                    if not cleaned and config.gemini_ocr_enabled and config.gemini_api_key:
                        cleaned = ocr_page_image(page)
                    if cleaned:
                        total_chars += len(cleaned)
                        if total_chars > max_chars:
                            raise ValueError(
                                f"Extracted text exceeds the {max_chars // 1_000_000} million character limit. Split this document."
                            )
                        segments.append({"text": cleaned, "page": i + 1})

        elif extension == ".docx":
            doc = (
                WordDocument(str(source))
                if isinstance(source, (str, Path))
                else WordDocument(BytesIO(source))
            )
            paragraphs = [paragraph.text for paragraph in doc.paragraphs]
            paragraphs += [
                " | ".join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows
            ]
            cleaned = clean_text("\n\n".join(paragraphs))
            if cleaned:
                if len(cleaned) > max_chars:
                    raise ValueError(
                        f"Extracted text exceeds the {max_chars // 1_000_000} million character limit. Split this document."
                    )
                segments.append({"text": cleaned, "page": 0})

        elif extension in {".txt", ".md", ".markdown"}:
            raw_text = (
                Path(source).read_text(encoding="utf-8-sig")
                if isinstance(source, (str, Path))
                else source.decode("utf-8-sig")
            )
            cleaned = clean_text(raw_text)
            if cleaned:
                if len(cleaned) > max_chars:
                    raise ValueError(
                        f"Extracted text exceeds the {max_chars // 1_000_000} million character limit. Split this document."
                    )
                segments.append({"text": cleaned, "page": 0})
        else:
            raise ValueError("Supported files: PDF, DOCX, TXT, and Markdown.")

    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError(
            str(error) if isinstance(error, ValueError) else "Save text files as UTF-8."
        ) from error
    except Exception as error:
        raise ValueError("This file is damaged or its contents do not match its extension.") from error

    if not segments:
        raise ValueError("No readable text found. Scanned PDFs need OCR before upload.")

    return segments


def chunk_text(segments: list[dict]) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    return [
        {"text": chunk, "page": segment["page"]}
        for segment in segments
        for chunk in splitter.split_text(segment["text"])
    ]


def upload_document(
    db,
    vectors,
    data_dir,
    workspace_id,
    name,
    content_or_path: bytes | Path | str,
    file_size: int | None = None,
    content_hash: str | None = None,
):
    """Validate, prevent duplicates, persist the original, then index extracted chunks."""
    name = name.replace("\\", "/").rsplit("/", 1)[-1][:240]
    extension = Path(name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Supported files: PDF, DOCX, TXT, and Markdown.")

    is_path = isinstance(content_or_path, (str, Path))
    if is_path:
        file_path = Path(content_or_path)
        if file_size is None:
            file_size = file_path.stat().st_size
        if content_hash is None:
            hasher = hashlib.sha256()
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            content_hash = hasher.hexdigest()
    else:
        file_size = len(content_or_path)
        content_hash = hashlib.sha256(content_or_path).hexdigest()

    existing = db.scalar(
        select(Document).where(Document.workspace_id == workspace_id, Document.content_hash == content_hash)
    )
    if existing:
        if is_path:
            Path(content_or_path).unlink(missing_ok=True)
        return existing, True

    log_stage_memory("before_extract_text", doc_name=name)
    segments = extract_text(content_or_path, extension)
    log_stage_memory("after_extract_text", doc_name=name, segment_count=len(segments))

    document = Document(
        id=new_id(),
        workspace_id=workspace_id,
        name=name,
        content_hash=content_hash,
        size=file_size,
        text="\n\n".join(segment["text"] for segment in segments),
    )
    db.add(document)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if is_path:
            Path(content_or_path).unlink(missing_ok=True)
        return db.scalar(
            select(Document).where(
                Document.workspace_id == workspace_id, Document.content_hash == content_hash
            )
        ), True

    try:
        storage.upload_file(workspace_id, document.id, content_or_path)
        index_document(db, vectors, document, segments)
    except Exception as error:
        logging.getLogger("aether").warning(
            "Indexing document %s failed: %s", document.id, type(error).__name__
        )
        document.status = "error"
        document.error = (
            "Indexing failed. Check local model download, disk space, and backend logs; then reindex."
        )
        db.commit()
    finally:
        del segments
        check_and_collect_garbage(threshold_mb=config.gc_threshold_mb)

    return document, False


def index_document(db, vectors, document, segments):
    """Stage a new version. Keep the previous index if rebuilding fails."""
    with vectors.lock:
        version = uuid4().hex
        previous_version = document.index_version
        chunks = chunk_text(segments)
        try:
            vectors.index(document.workspace_id, document.id, document.name, chunks, version)
        except Exception:
            vectors.delete_document(document.workspace_id, document.id, version)
            raise
        document.index_version = version
        document.chunk_count = len(chunks)
        document.status = "ready"
        document.error = None
        try:
            db.commit()
        except Exception:
            db.rollback()
            vectors.delete_document(document.workspace_id, document.id, version)
            raise
        if previous_version:
            vectors.delete_document(document.workspace_id, document.id, previous_version)
        del chunks
        check_and_collect_garbage(threshold_mb=config.gc_threshold_mb)
