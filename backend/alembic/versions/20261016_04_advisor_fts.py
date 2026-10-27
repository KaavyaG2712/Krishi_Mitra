"""Add local full-text search for the agronomy knowledge base.

Revision ID: 20261016_04
Revises: 20260913_03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261016_04"
down_revision: Union[str, Sequence[str], None] = "20260913_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep the old vector fields nullable for existing installations, but drop
    # their unused HNSW index to avoid carrying vector-search storage costs.
    op.drop_index("ix_knowledge_chunks_embedding_hnsw", table_name="knowledge_chunks")
    op.alter_column("knowledge_chunks", "embedding", existing_type=Vector(dim=768), nullable=True)
    op.alter_column("knowledge_chunks", "embedding_model", existing_type=sa.String(length=128), nullable=True)
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple'::regconfig, coalesce(chunk_text, ''::text))", persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_search_vector",
        "knowledge_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_search_vector", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "search_vector")
    connection = op.get_bind()
    nullable_embeddings = connection.execute(
        sa.text("SELECT count(*) FROM knowledge_chunks WHERE embedding IS NULL")
    ).scalar_one()
    if nullable_embeddings:
        raise RuntimeError("Cannot downgrade while local FTS knowledge chunks have no embeddings.")
    op.alter_column("knowledge_chunks", "embedding", existing_type=Vector(dim=768), nullable=False)
    op.alter_column("knowledge_chunks", "embedding_model", existing_type=sa.String(length=128), nullable=False)
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
