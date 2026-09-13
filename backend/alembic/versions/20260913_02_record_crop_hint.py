"""Record crop-hint validation on disease scans.

Revision ID: 20260913_02
Revises: 20260913_01
Create Date: 2026-09-13
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260913_02"
down_revision: Union[str, Sequence[str], None] = "20260913_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("disease_scans", sa.Column("crop_hint", sa.String(length=32), nullable=True))
    op.add_column(
        "disease_scans",
        sa.Column("crop_mismatch", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("disease_scans", "crop_mismatch", server_default=None)


def downgrade() -> None:
    op.drop_column("disease_scans", "crop_mismatch")
    op.drop_column("disease_scans", "crop_hint")
