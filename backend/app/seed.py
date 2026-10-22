"""Question-bank seed validation and idempotent loading.

The seed file (``data/seed/questions.json``) is produced from the source PDF by
``scripts/extract_questions.py``. This module never reads the PDF.
"""

from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Option, Question, SeedImport

EXPECTED_WEEKS = 12
EXPECTED_PER_WEEK = 10
EXPECTED_TOTAL = EXPECTED_WEEKS * EXPECTED_PER_WEEK
OPTIONS_PER_QUESTION = 4


class SeedValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__(f"{len(errors)} seed validation error(s)")
        self.errors = errors


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    week_counts: dict[int, int] = field(default_factory=dict)
    question_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def load_seed_document(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_seed_document(doc: dict, audit_rows: list[dict] | None = None) -> ValidationResult:
    """Validate the seed document's structure, answer key, and audit coverage."""
    result = ValidationResult()
    errs = result.errors
    questions = doc.get("questions")
    if not isinstance(questions, list):
        errs.append("seed document has no 'questions' list")
        return result

    result.question_count = len(questions)
    seen_ident: set[tuple[int, int]] = set()
    seen_qid: set[str] = set()
    seen_oid: set[str] = set()

    for q in questions:
        week, qno = q.get("source_week"), q.get("source_question_no")
        tag = f"W{week} Q{qno}"
        if not isinstance(week, int) or not 1 <= week <= EXPECTED_WEEKS:
            errs.append(f"{tag}: invalid source_week")
            continue
        if not isinstance(qno, int) or not 1 <= qno <= EXPECTED_PER_WEEK:
            errs.append(f"{tag}: invalid source_question_no")
            continue
        if (week, qno) in seen_ident:
            errs.append(f"{tag}: duplicate (week, question_number)")
        seen_ident.add((week, qno))
        result.week_counts[week] = result.week_counts.get(week, 0) + 1

        qid = q.get("id")
        if not _is_uuid(qid):
            errs.append(f"{tag}: missing or invalid question id")
        elif qid in seen_qid:
            errs.append(f"{tag}: duplicate question id {qid}")
        seen_qid.add(qid)

        if not str(q.get("question_text", "")).strip():
            errs.append(f"{tag}: blank question text")

        options = q.get("options") or []
        if len(options) != OPTIONS_PER_QUESTION:
            errs.append(f"{tag}: expected {OPTIONS_PER_QUESTION} options, found {len(options)}")
        correct = [o for o in options if o.get("is_correct") is True]
        if len(correct) != 1:
            errs.append(f"{tag}: expected exactly 1 correct option, found {len(correct)}")
        for o in options:
            oid = o.get("id")
            if not _is_uuid(oid):
                errs.append(f"{tag}: option with missing or invalid id")
            elif oid in seen_oid:
                errs.append(f"{tag}: duplicate option id {oid}")
            seen_oid.add(oid)
            if not str(o.get("option_text", "")).strip():
                errs.append(f"{tag}: blank option text ({o.get('source_label')})")
            if o.get("is_correct") and not o.get("source_was_bold"):
                errs.append(f"{tag}: correct option is not marked as bold in the source")
        texts = [str(o.get("option_text", "")).strip().casefold() for o in options]
        if len(set(texts)) != len(texts):
            errs.append(f"{tag}: duplicate option text within the question")

        audit = q.get("audit") or {}
        if audit.get("verification_status") != "verified":
            errs.append(f"{tag}: answer verification status is {audit.get('verification_status')!r}, not 'verified'")
        if audit.get("issues"):
            errs.append(f"{tag}: unresolved import issues: {audit['issues']}")

    for w in range(1, EXPECTED_WEEKS + 1):
        if result.week_counts.get(w, 0) != EXPECTED_PER_WEEK:
            errs.append(f"Week {w}: expected {EXPECTED_PER_WEEK} questions, found {result.week_counts.get(w, 0)}")
    if len(questions) != EXPECTED_TOTAL:
        errs.append(f"expected {EXPECTED_TOTAL} questions, found {len(questions)}")

    if audit_rows is not None:
        _validate_audit(questions, audit_rows, errs)
    return result


def _validate_audit(questions: list[dict], rows: list[dict], errs: list[str]) -> None:
    by_ident = {}
    for row in rows:
        try:
            ident = (int(row["week"]), int(row["question_no"]))
        except (KeyError, ValueError):
            errs.append(f"audit: malformed row {row!r}")
            continue
        if ident in by_ident:
            errs.append(f"audit: duplicate row for W{ident[0]} Q{ident[1]}")
        by_ident[ident] = row
    for q in questions:
        ident = (q.get("source_week"), q.get("source_question_no"))
        row = by_ident.pop(ident, None)
        tag = f"W{ident[0]} Q{ident[1]}"
        if row is None:
            errs.append(f"audit: no row for {tag}")
            continue
        correct = [o for o in q.get("options", []) if o.get("is_correct")]
        if len(correct) == 1:
            if row.get("correct_option_id") != correct[0].get("id"):
                errs.append(f"audit: {tag} correct_option_id does not match the seed")
            if (row.get("correct_option_text") or "").strip() != correct[0].get("option_text", "").strip():
                errs.append(f"audit: {tag} correct_option_text does not match the seed")
        if row.get("question_id") != q.get("id"):
            errs.append(f"audit: {tag} question_id does not match the seed")
        if row.get("verification_status") != "verified":
            errs.append(f"audit: {tag} verification_status is {row.get('verification_status')!r}")
    for ident in by_ident:
        errs.append(f"audit: row W{ident[0]} Q{ident[1]} has no matching seed question")


def load_audit_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _is_uuid(value: object) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def seed_database(session: Session, seed_path: Path, audit_path: Path) -> dict:
    """Validate the seed files, then upsert them in one transaction.

    Re-running with the same file is a no-op apart from refreshing values; IDs are
    stable, so no duplicates are created. Questions not present in the file are
    deactivated rather than deleted, so historical attempts remain valid.
    """
    raw = seed_path.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    audit_rows = load_audit_rows(audit_path)
    validation = validate_seed_document(doc, audit_rows)
    if not validation.ok:
        raise SeedValidationError(validation.errors)

    seed_sha = hashlib.sha256(raw).hexdigest()
    question_ids = []
    for q in doc["questions"]:
        qid = uuid.UUID(q["id"])
        question_ids.append(qid)
        stmt = insert(Question).values(
            id=qid,
            source_week=q["source_week"],
            source_question_no=q["source_question_no"],
            question_text=q["question_text"],
            source_pdf_page=q.get("source_pdf_page"),
            is_active=True,
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Question.id],
                set_={
                    "source_week": stmt.excluded.source_week,
                    "source_question_no": stmt.excluded.source_question_no,
                    "question_text": stmt.excluded.question_text,
                    "source_pdf_page": stmt.excluded.source_pdf_page,
                    "is_active": True,
                    "updated_at": func.now(),
                },
                where=(
                    (Question.question_text != stmt.excluded.question_text)
                    | (Question.source_pdf_page.is_distinct_from(stmt.excluded.source_pdf_page))
                    | (Question.is_active.is_(False))
                ),
            )
        )
        # Clear the correct flag first so the partial unique index
        # (one correct option per question) is never violated mid-update.
        session.execute(update(Option).where(Option.question_id == qid).values(is_correct=False))
        for o in q["options"]:
            ostmt = insert(Option).values(
                id=uuid.UUID(o["id"]),
                question_id=qid,
                option_text=o["option_text"],
                source_label=o.get("source_label"),
                is_correct=bool(o["is_correct"]),
                source_was_bold=bool(o.get("source_was_bold")),
            )
            session.execute(
                ostmt.on_conflict_do_update(
                    index_elements=[Option.id],
                    set_={
                        "option_text": ostmt.excluded.option_text,
                        "source_label": ostmt.excluded.source_label,
                        "is_correct": ostmt.excluded.is_correct,
                        "source_was_bold": ostmt.excluded.source_was_bold,
                    },
                )
            )

    deactivated = session.execute(
        update(Question).where(Question.id.not_in(question_ids), Question.is_active.is_(True)).values(is_active=False)
    ).rowcount

    marker = insert(SeedImport).values(
        seed_sha256=seed_sha,
        source_pdf_sha256=doc.get("source", {}).get("sha256", ""),
        question_count=len(question_ids),
    )
    session.execute(marker.on_conflict_do_nothing(index_elements=[SeedImport.seed_sha256]))

    db_errors = validate_database(session)
    if db_errors:
        raise SeedValidationError(db_errors)
    return {"questions": len(question_ids), "deactivated": deactivated, "seed_sha256": seed_sha}


def validate_database(session: Session) -> list[str]:
    """Run the integrity checks from Backend_DB_Schema.md section 5 against the database."""
    errors: list[str] = []
    rows = session.execute(
        select(
            Question.source_week,
            Question.source_question_no,
            func.count(Option.id),
            func.count(Option.id).filter(Option.is_correct),
        )
        .outerjoin(Option, Option.question_id == Question.id)
        .where(Question.is_active.is_(True))
        .group_by(Question.id, Question.source_week, Question.source_question_no)
    ).all()
    for week, qno, n_opts, n_correct in rows:
        if n_opts != OPTIONS_PER_QUESTION or n_correct != 1:
            errors.append(f"DB W{week} Q{qno}: {n_opts} options, {n_correct} correct")

    week_counts = dict(
        session.execute(
            select(Question.source_week, func.count())
            .where(Question.is_active.is_(True))
            .group_by(Question.source_week)
        ).all()
    )
    for w in range(1, EXPECTED_WEEKS + 1):
        if week_counts.get(w, 0) != EXPECTED_PER_WEEK:
            errors.append(f"DB week {w}: {week_counts.get(w, 0)} active questions (expected {EXPECTED_PER_WEEK})")
    total = sum(week_counts.values())
    if total != EXPECTED_TOTAL:
        errors.append(f"DB: {total} active questions (expected {EXPECTED_TOTAL})")
    return errors
