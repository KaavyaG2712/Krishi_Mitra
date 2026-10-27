"""Extract cited, page-aware passages from approved local agriculture PDFs.

PDF files stay outside Git. The manifest is a local JSON file, and documents
are inserted into PostgreSQL only after their source metadata is reviewed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import KnowledgeChunk, KnowledgeDocument

MAX_WORDS = 240
OVERLAP_WORDS = 35


def split_page(text: str) -> list[str]:
    words = re.sub(r"\s+", " ", text).strip().split()
    if not words:
        return []
    passages: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + MAX_WORDS, len(words))
        passage = " ".join(words[start:end]).strip()
        if len(passage) >= 25:
            passages.append(passage)
        if end == len(words):
            break
        start = end - OVERLAP_WORDS
    return passages


def read_manifest(path: Path) -> list[dict]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    documents = manifest.get("documents") if isinstance(manifest, dict) else None
    if not isinstance(documents, list):
        raise ValueError("Manifest must contain a 'documents' array.")
    return documents


def extract_document(item: dict, manifest_path: Path) -> tuple[dict, list[dict]]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError('Install the optional PDF parser with `python -m pip install -e ".[corpus]"`.') from error
    for field in ("file", "title", "publisher", "source_url", "tags"):
        if not item.get(field):
            raise ValueError(f"Each document needs a non-empty '{field}'.")
    source_path = (manifest_path.parent / item["file"]).resolve()
    if not source_path.is_file() or source_path.suffix.lower() != ".pdf":
        raise ValueError(f"Approved PDF was not found: {source_path}")
    if not str(item["source_url"]).startswith("https://"):
        raise ValueError("Knowledge sources must use a verified HTTPS URL.")
    raw = source_path.read_bytes()
    reader = PdfReader(source_path)
    if reader.is_encrypted:
        raise ValueError(f"Encrypted PDFs are not supported: {source_path.name}")

    checksum = hashlib.sha256(raw).hexdigest()
    metadata = {
        "title": item["title"],
        "publisher": item["publisher"],
        "source_url": item["source_url"],
        "licence": item.get("licence"),
        "checksum": checksum,
    }
    passages: list[dict] = []
    page_offset = int(item.get("page_offset", 0))
    for pdf_index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        for chunk_index, text in enumerate(split_page(page_text), start=1):
            passages.append(
                {
                    "page_number": pdf_index + page_offset,
                    "text": text,
                    "metadata_json": {
                        "tags": item["tags"],
                        "section": item.get("section"),
                        "language": item.get("language", "en"),
                        "content_kind": "source_pdf_extraction",
                        "pdf_page_index": pdf_index,
                        "chunk_on_page": chunk_index,
                    },
                }
            )
    return metadata, passages


def store_document(db, metadata: dict, passages: list[dict]) -> tuple[bool, int]:
    checksum = metadata["checksum"]
    if db.scalar(select(KnowledgeDocument.id).where(KnowledgeDocument.checksum == checksum)):
        return False, 0
    document = KnowledgeDocument(
        title=metadata["title"],
        publisher=metadata["publisher"],
        source_url=metadata["source_url"],
        licence=metadata.get("licence"),
        checksum=checksum,
    )
    db.add(document)
    db.flush()
    for passage in passages:
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                page_number=passage["page_number"],
                chunk_text=passage["text"],
                embedding=None,
                embedding_model=None,
                metadata_json=passage["metadata_json"],
            )
        )
    return True, len(passages)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("../data/raw/corpus/manifest.json"),
        help="Local manifest path; PDF paths are resolved relative to the manifest.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Extract and count passages without writing to PostgreSQL.")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    documents = read_manifest(manifest_path)
    extracted = [extract_document(item, manifest_path) for item in documents]
    if args.dry_run:
        print(f"Validated {len(extracted)} PDFs; extracted {sum(len(p) for _, p in extracted)} page-aware passages.")
        return

    added_documents = 0
    added_passages = 0
    with SessionLocal() as db:
        try:
            for metadata, passages in extracted:
                if not passages:
                    print(f"Skipped {metadata['title']}: no extractable text was found.")
                    continue
                added, count = store_document(db, metadata, passages)
                added_documents += int(added)
                added_passages += count
            db.commit()
        except Exception:
            db.rollback()
            raise
    print(f"Ingested {added_passages} passages from {added_documents} new source PDFs.")


if __name__ == "__main__":
    main()
