"""Migrations, seeding, and database-level integrity constraints."""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models import Option, Question, SeedImport
from app.seed import seed_database, validate_database


def test_migrated_and_seeded_bank_passes_integrity_checks(db):
    assert validate_database(db) == []
    assert db.scalar(select(func.count()).select_from(Question)) == 120
    assert db.scalar(select(func.count()).select_from(Option)) == 480
    weeks = dict(db.execute(select(Question.source_week, func.count()).group_by(Question.source_week)).all())
    assert weeks == {w: 10 for w in range(1, 13)}


def test_seeding_is_idempotent(session_factory):
    s = get_settings()
    for _ in range(2):
        with session_factory() as session:
            summary = seed_database(session, s.seed_file, s.audit_file)
            session.commit()
        assert summary["questions"] == 120
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Question)) == 120
        assert session.scalar(select(func.count()).select_from(Option)) == 480
        assert session.scalar(select(func.count()).select_from(Option).where(Option.is_correct)) == 120
        assert session.scalar(select(func.count()).select_from(SeedImport)) == 1
        assert validate_database(session) == []


def test_question_ids_are_stable_across_reseed(session_factory):
    with session_factory() as session:
        before = set(session.scalars(select(Option.id)).all())
    s = get_settings()
    with session_factory() as session:
        seed_database(session, s.seed_file, s.audit_file)
        session.commit()
    with session_factory() as session:
        assert set(session.scalars(select(Option.id)).all()) == before


def test_database_rejects_second_correct_option(db):
    q = db.scalars(select(Question).limit(1)).first()
    wrong = next(o for o in q.options if not o.is_correct)
    wrong.is_correct = True
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def _one_attempt_question(db):
    db.execute(
        text(
            "INSERT INTO quiz_attempts (id, access_token_hash, mode, week_no, total_questions) "
            "VALUES (:id, 'x', 'weekly', 1, 10)"
        ),
        {"id": (aid := uuid.uuid4())},
    )
    q1, q2 = db.scalars(select(Question).where(Question.source_week == 1).limit(2)).all()
    aq = uuid.uuid4()
    db.execute(
        text("INSERT INTO attempt_questions (id, attempt_id, question_id, display_order) VALUES (:id, :a, :q, 1)"),
        {"id": aq, "a": aid, "q": q1.id},
    )
    return aq, q1, q2


def test_database_rejects_selected_option_from_another_question(db):
    aq, _, q2 = _one_attempt_question(db)
    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE attempt_questions SET selected_option_id = :o WHERE id = :id"),
            {"o": q2.options[0].id, "id": aq},
        )
    db.rollback()


def test_database_rejects_displayed_option_from_another_question(db):
    aq, q1, q2 = _one_attempt_question(db)
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO attempt_question_options (attempt_question_id, option_id, question_id, display_order) "
                "VALUES (:aq, :o, :q, 1)"
            ),
            {"aq": aq, "o": q2.options[0].id, "q": q1.id},
        )
    db.rollback()


def test_database_rejects_inconsistent_attempt_mode(db):
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO quiz_attempts (id, access_token_hash, mode, week_no, total_questions) "
                "VALUES (:id, 'x', 'overall', 3, 120)"
            ),
            {"id": uuid.uuid4()},
        )
    db.rollback()
