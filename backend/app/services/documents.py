"""This file handles document uploads and indexing in Aether AI. It accepts PDF, Word, text, and Markdown files, extracts their text, splits it into smaller chunks, stores the document in the database, and indexes the chunks for AI search (RAG)."""


# clean_text()	Removes unwanted characters and extra spaces while preserving paragraphs.
# extract_text()	Extracts readable text from PDF, DOCX, TXT, and Markdown files. uses clean_text()
# chunk_text()	Splits extracted text into smaller chunks of 800 characters, with 150 characters of overlap.
# upload_document()	Main upload function. Validates files, detects duplicates, saves the document, and starts indexing.
# index_document()	Indexes document chunks in the vector store and updates the database with indexing status.
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

from app.models.database import Document, new_id

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


def clean_text(text: str) -> str:
    """Remove nulls and repeated spaces while preserving paragraph boundaries."""
    text = text.replace("\x00", "").replace("\r\n", "\n")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def extract_text(content: bytes, extension: str) -> list[dict]: 
    """Extract page-aware PDF text, Word paragraphs/tables, or UTF-8 plain text."""
    try:
        if extension == ".pdf":
            with pymupdf.open(stream=content, filetype="pdf") as pdf:
                if pdf.is_encrypted:
                    raise ValueError("Password-protected PDFs are not supported.")
                segments = [
                    {"text": clean_text(page.get_text()), "page": i + 1} for i, page in enumerate(pdf)
                ]
        elif extension == ".docx":
            doc = WordDocument(BytesIO(content))
            paragraphs = [paragraph.text for paragraph in doc.paragraphs]
            paragraphs += [
                " | ".join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows
            ]
            segments = [{"text": clean_text("\n\n".join(paragraphs)), "page": 0}]
        elif extension in {".txt", ".md", ".markdown"}:
            segments = [{"text": clean_text(content.decode("utf-8-sig")), "page": 0}]
        else:
            raise ValueError("Supported files: PDF, DOCX, TXT, and Markdown.")
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError(
            str(error) if isinstance(error, ValueError) else "Save text files as UTF-8."
        ) from error
    except Exception as error:
        raise ValueError("This file is damaged or its contents do not match its extension.") from error
    segments = [segment for segment in segments if segment["text"]]
    if not segments:
        raise ValueError("No readable text found. Scanned PDFs need OCR before upload.")
    if sum(len(segment["text"]) for segment in segments) > 2_000_000:
        raise ValueError("Extracted text exceeds the 2 million character limit. Split this document.")
    return segments


def chunk_text(segments: list[dict]) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    return [
        {"text": chunk, "page": segment["page"]}
        for segment in segments
        for chunk in splitter.split_text(segment["text"])
    ]

# uses model db, extract_text(),
def upload_document(db, vectors, data_dir, workspace_id, name, content):
    """Validate, prevent duplicates, persist the original, then index extracted chunks."""
    name = name.replace("\\", "/").rsplit("/", 1)[-1][:240]
    extension = Path(name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Supported files: PDF, DOCX, TXT, and Markdown.")
    content_hash = hashlib.sha256(content).hexdigest()
    existing = db.scalar(
        select(Document).where(Document.workspace_id == workspace_id, Document.content_hash == content_hash)
    )
    if existing:
        return existing, True
    segments = extract_text(content, extension)
    document = Document(
        id=new_id(),
        workspace_id=workspace_id,
        name=name,
        content_hash=content_hash,
        size=len(content),
        text="\n\n".join(segment["text"] for segment in segments),
    )
    db.add(document)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(
            select(Document).where(
                Document.workspace_id == workspace_id, Document.content_hash == content_hash
            )
        ), True
    folder = data_dir / "uploads" / workspace_id
    folder.mkdir(parents=True, exist_ok=True)
    try:
        (folder / document.id).write_bytes(content)
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
    return document, False

# uses chunks_text()
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
