"""Load the small reviewed starter knowledge set into local PostgreSQL."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import KnowledgeChunk, KnowledgeDocument

SEED_FILE = Path(__file__).with_name("data") / "seed_knowledge.json"


def seed_knowledge(db: Session) -> tuple[int, int]:
    catalog = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    documents_added = 0
    chunks_added = 0
    for source in catalog["documents"]:
        content = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = db.scalar(select(KnowledgeDocument.id).where(KnowledgeDocument.checksum == checksum))
        if existing:
            continue

        document = KnowledgeDocument(
            title=source["title"],
            publisher=source["publisher"],
            source_url=source["source_url"],
            licence=source.get("licence"),
            checksum=checksum,
        )
        db.add(document)
        db.flush()
        documents_added += 1
        for passage in source["passages"]:
            db.add(
                KnowledgeChunk(
                    document_id=document.id,
                    page_number=passage.get("page_number"),
                    chunk_text=passage["text"].strip(),
                    embedding=None,
                    embedding_model=None,
                    metadata_json={
                        "tags": source.get("tags", []),
                        "section": passage.get("section"),
                        "language": "en",
                        "content_kind": "reviewed_paraphrase",
                    },
                )
            )
            chunks_added += 1
    db.commit()
    return documents_added, chunks_added


def main() -> None:
    with SessionLocal() as db:
        documents_added, chunks_added = seed_knowledge(db)
    print(f"Local advisor library ready: added {documents_added} sources and {chunks_added} passages.")


if __name__ == "__main__":
    main()
