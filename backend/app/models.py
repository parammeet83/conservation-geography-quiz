"""SQLAlchemy ORM models.

The canonical question bank (questions, options) is separate from the
per-attempt randomised presentation (attempt_questions, attempt_question_options).
Correctness lives only on ``options.is_correct``; it is never tied to a display
position or label.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("source_week", "source_question_no", name="uq_question_source"),
        CheckConstraint("source_week BETWEEN 1 AND 12", name="ck_question_week"),
        CheckConstraint("source_question_no BETWEEN 1 AND 10", name="ck_question_no"),
        CheckConstraint("length(trim(question_text)) > 0", name="ck_question_text_nonblank"),
        CheckConstraint("source_pdf_page BETWEEN 1 AND 26", name="ck_question_pdf_page"),
        Index("ix_questions_active_week", "is_active", "source_week"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    source_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_question_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(Text)
    source_pdf_page: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    options: Mapped[list["Option"]] = relationship(back_populates="question", order_by="Option.source_label")


class Option(Base):
    __tablename__ = "options"
    __table_args__ = (
        UniqueConstraint("question_id", "id", name="uq_option_question_pair"),
        CheckConstraint("length(trim(option_text)) > 0", name="ck_option_text_nonblank"),
        Index("ix_options_question_id", "question_id"),
        # At most one correct option per question, enforced by the database.
        # "Exactly one" is enforced by seed validation and tests.
        Index("uq_options_one_correct", "question_id", unique=True, postgresql_where=text("is_correct")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    option_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_label: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    source_was_bold: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    question: Mapped[Question] = relationship(back_populates="options")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        CheckConstraint("mode IN ('weekly', 'overall')", name="ck_attempt_mode"),
        CheckConstraint("status IN ('in_progress', 'submitted', 'abandoned')", name="ck_attempt_status"),
        CheckConstraint("total_questions IN (10, 120)", name="ck_attempt_total"),
        CheckConstraint("score_correct BETWEEN 0 AND total_questions", name="ck_attempt_score_range"),
        CheckConstraint("score_percent BETWEEN 0 AND 100", name="ck_attempt_percent_range"),
        CheckConstraint(
            "(mode = 'weekly' AND week_no BETWEEN 1 AND 12 AND total_questions = 10)"
            " OR (mode = 'overall' AND week_no IS NULL AND total_questions = 120)",
            name="ck_attempt_mode_week",
        ),
        CheckConstraint(
            "(status = 'submitted' AND submitted_at IS NOT NULL"
            " AND score_correct IS NOT NULL AND score_percent IS NOT NULL)"
            " OR (status <> 'submitted' AND submitted_at IS NULL)",
            name="ck_attempt_submission_state",
        ),
        Index("ix_attempts_status_started", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    access_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    week_no: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'in_progress'"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    score_correct: Mapped[int | None] = mapped_column(Integer)
    score_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    questions: Mapped[list["AttemptQuestion"]] = relationship(
        back_populates="attempt", order_by="AttemptQuestion.display_order", cascade="all, delete-orphan"
    )


class AttemptQuestion(Base):
    __tablename__ = "attempt_questions"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),
        UniqueConstraint("attempt_id", "display_order", name="uq_attempt_question_order"),
        UniqueConstraint("id", "question_id", name="uq_attempt_question_id_question"),
        CheckConstraint("display_order >= 1", name="ck_attempt_question_order"),
        # A selected option must belong to this attempt question's canonical question.
        ForeignKeyConstraint(
            ["question_id", "selected_option_id"],
            ["options.question_id", "options.id"],
            name="fk_selected_option_for_this_question",
        ),
        Index("ix_attempt_questions_attempt_order", "attempt_id", "display_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_option_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempt: Mapped[QuizAttempt] = relationship(back_populates="questions")
    question: Mapped[Question] = relationship()
    option_order: Mapped[list["AttemptQuestionOption"]] = relationship(
        order_by="AttemptQuestionOption.display_order",
        cascade="all, delete-orphan",
        primaryjoin="AttemptQuestion.id == AttemptQuestionOption.attempt_question_id",
        foreign_keys="AttemptQuestionOption.attempt_question_id",
    )


class AttemptQuestionOption(Base):
    __tablename__ = "attempt_question_options"
    __table_args__ = (
        UniqueConstraint("attempt_question_id", "display_order", name="uq_attempt_option_order"),
        CheckConstraint("display_order BETWEEN 1 AND 4", name="ck_attempt_option_order"),
        # Both composite FKs guarantee the displayed option belongs to the same
        # canonical question as its attempt question.
        ForeignKeyConstraint(
            ["attempt_question_id", "question_id"],
            ["attempt_questions.id", "attempt_questions.question_id"],
            ondelete="CASCADE",
            name="fk_aqo_attempt_question",
        ),
        ForeignKeyConstraint(
            ["question_id", "option_id"],
            ["options.question_id", "options.id"],
            name="fk_aqo_option_same_question",
        ),
    )

    attempt_question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    option_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    option: Mapped[Option] = relationship(
        primaryjoin="AttemptQuestionOption.option_id == Option.id",
        foreign_keys=[option_id],
        viewonly=True,
    )


class SeedImport(Base):
    """Import-version marker: one row per distinct seed file loaded."""

    __tablename__ = "seed_imports"

    seed_sha256: Mapped[str] = mapped_column(Text, primary_key=True)
    source_pdf_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
