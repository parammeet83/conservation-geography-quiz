"""Add quiz_attempts.study_mode for Study Mode attempts.

Existing attempts default to false (Quiz Mode), so their behaviour is unchanged.

Revision ID: 0002_attempt_study_mode
Revises: 0001_initial_schema
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_attempt_study_mode"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quiz_attempts",
        sa.Column("study_mode", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("quiz_attempts", "study_mode")
