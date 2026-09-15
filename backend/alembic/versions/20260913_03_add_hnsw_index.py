"""Add cosine HNSW index for advisor retrieval.

Revision ID: 20260913_03
Revises: 20260913_02
Create Date: 2026-09-13
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "20260913_03"
down_revision: Union[str, Sequence[str], None] = "20260913_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_knowledge_chunks_embedding_hnsw")
