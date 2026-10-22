"""Initial schema: question bank, attempts, randomised order, seed import marker.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("source_week", sa.SmallInteger, nullable=False),
        sa.Column("source_question_no", sa.SmallInteger, nullable=False),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("topic", sa.Text),
        sa.Column("source_pdf_page", sa.SmallInteger),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("source_week", "source_question_no", name="uq_question_source"),
        sa.CheckConstraint("source_week BETWEEN 1 AND 12", name="ck_question_week"),
        sa.CheckConstraint("source_question_no BETWEEN 1 AND 10", name="ck_question_no"),
        sa.CheckConstraint("length(trim(question_text)) > 0", name="ck_question_text_nonblank"),
        sa.CheckConstraint("source_pdf_page BETWEEN 1 AND 26", name="ck_question_pdf_page"),
    )
    op.create_index("ix_questions_active_week", "questions", ["is_active", "source_week"])

    op.create_table(
        "options",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("question_id", UUID, sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("option_text", sa.Text, nullable=False),
        sa.Column("source_label", sa.Text),
        sa.Column("is_correct", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("source_was_bold", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("question_id", "id", name="uq_option_question_pair"),
        sa.CheckConstraint("length(trim(option_text)) > 0", name="ck_option_text_nonblank"),
    )
    op.create_index("ix_options_question_id", "options", ["question_id"])
    op.create_index(
        "uq_options_one_correct", "options", ["question_id"], unique=True, postgresql_where=sa.text("is_correct")
    )

    op.create_table(
        "quiz_attempts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("access_token_hash", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("week_no", sa.SmallInteger),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'in_progress'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("total_questions", sa.Integer, nullable=False),
        sa.Column("score_correct", sa.Integer),
        sa.Column("score_percent", sa.Numeric(5, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("mode IN ('weekly', 'overall')", name="ck_attempt_mode"),
        sa.CheckConstraint("status IN ('in_progress', 'submitted', 'abandoned')", name="ck_attempt_status"),
        sa.CheckConstraint("total_questions IN (10, 120)", name="ck_attempt_total"),
        sa.CheckConstraint("score_correct BETWEEN 0 AND total_questions", name="ck_attempt_score_range"),
        sa.CheckConstraint("score_percent BETWEEN 0 AND 100", name="ck_attempt_percent_range"),
        sa.CheckConstraint(
            "(mode = 'weekly' AND week_no BETWEEN 1 AND 12 AND total_questions = 10)"
            " OR (mode = 'overall' AND week_no IS NULL AND total_questions = 120)",
            name="ck_attempt_mode_week",
        ),
        sa.CheckConstraint(
            "(status = 'submitted' AND submitted_at IS NOT NULL"
            " AND score_correct IS NOT NULL AND score_percent IS NOT NULL)"
            " OR (status <> 'submitted' AND submitted_at IS NULL)",
            name="ck_attempt_submission_state",
        ),
    )
    op.create_index("ix_attempts_status_started", "quiz_attempts", ["status", "started_at"])

    op.create_table(
        "attempt_questions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("attempt_id", UUID, sa.ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", UUID, sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("selected_option_id", UUID),
        sa.Column("is_correct", sa.Boolean),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),
        sa.UniqueConstraint("attempt_id", "display_order", name="uq_attempt_question_order"),
        sa.UniqueConstraint("id", "question_id", name="uq_attempt_question_id_question"),
        sa.CheckConstraint("display_order >= 1", name="ck_attempt_question_order"),
        sa.ForeignKeyConstraint(
            ["question_id", "selected_option_id"],
            ["options.question_id", "options.id"],
            name="fk_selected_option_for_this_question",
        ),
    )
    op.create_index("ix_attempt_questions_attempt_order", "attempt_questions", ["attempt_id", "display_order"])

    op.create_table(
        "attempt_question_options",
        sa.Column("attempt_question_id", UUID, primary_key=True),
        sa.Column("option_id", UUID, primary_key=True),
        sa.Column("question_id", UUID, nullable=False),
        sa.Column("display_order", sa.SmallInteger, nullable=False),
        sa.UniqueConstraint("attempt_question_id", "display_order", name="uq_attempt_option_order"),
        sa.CheckConstraint("display_order BETWEEN 1 AND 4", name="ck_attempt_option_order"),
        sa.ForeignKeyConstraint(
            ["attempt_question_id", "question_id"],
            ["attempt_questions.id", "attempt_questions.question_id"],
            ondelete="CASCADE",
            name="fk_aqo_attempt_question",
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "option_id"],
            ["options.question_id", "options.id"],
            name="fk_aqo_option_same_question",
        ),
    )

    op.create_table(
        "seed_imports",
        sa.Column("seed_sha256", sa.Text, primary_key=True),
        sa.Column("source_pdf_sha256", sa.Text, nullable=False),
        sa.Column("question_count", sa.Integer, nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )


def downgrade() -> None:
    op.drop_table("seed_imports")
    op.drop_table("attempt_question_options")
    op.drop_index("ix_attempt_questions_attempt_order", table_name="attempt_questions")
    op.drop_table("attempt_questions")
    op.drop_index("ix_attempts_status_started", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
    op.drop_index("uq_options_one_correct", table_name="options")
    op.drop_index("ix_options_question_id", table_name="options")
    op.drop_table("options")
    op.drop_index("ix_questions_active_week", table_name="questions")
    op.drop_table("questions")
