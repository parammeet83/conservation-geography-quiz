"""Quiz business logic: catalogue, attempt creation, answer saving, grading."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.errors import ApiError
from app.models import AttemptQuestion, AttemptQuestionOption, Question, QuizAttempt
from app.security import hash_token, new_access_token, token_matches
from app.seed import EXPECTED_PER_WEEK, EXPECTED_TOTAL, EXPECTED_WEEKS
from app.shuffle import RandomSource, fisher_yates

logger = logging.getLogger("cgq.attempts")

LABELS = "ABCD"


def quiz_title(mode: str, week_no: int | None) -> str:
    return f"Week {week_no}" if mode == "weekly" else "Overall Quiz"


def percent(correct: int, total: int) -> Decimal:
    """Score percentage rounded half-up to two decimal places."""
    return (Decimal(correct) * 100 / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---- Catalogue -------------------------------------------------------------


def get_catalogue(session: Session) -> schemas.QuizCatalogue:
    """Counts come from validated active questions; a scope is available only when complete."""
    counts = dict(
        session.execute(
            select(Question.source_week, func.count())
            .where(Question.is_active.is_(True))
            .group_by(Question.source_week)
        ).all()
    )
    weeks = [
        schemas.WeekQuiz(
            week_no=w,
            title=f"Week {w}",
            question_count=counts.get(w, 0),
            available=counts.get(w, 0) == EXPECTED_PER_WEEK,
        )
        for w in range(1, EXPECTED_WEEKS + 1)
    ]
    total = sum(counts.values())
    overall = schemas.OverallQuiz(
        title="Overall Quiz",
        question_count=total,
        available=total == EXPECTED_TOTAL and all(w.available for w in weeks),
    )
    return schemas.QuizCatalogue(weeks=weeks, overall=overall)


# ---- Attempt creation --------------------------------------------------------


def create_attempt(session: Session, req: schemas.CreateAttemptRequest, rng: RandomSource) -> tuple[QuizAttempt, str]:
    stmt = select(Question).options(selectinload(Question.options)).where(Question.is_active.is_(True))
    expected = EXPECTED_TOTAL
    if req.mode == "weekly":
        stmt = stmt.where(Question.source_week == req.week_no)
        expected = EXPECTED_PER_WEEK
    # Deterministic input order, so an injected test RNG gives reproducible permutations.
    questions = session.scalars(stmt.order_by(Question.source_week, Question.source_question_no)).all()

    if len(questions) != expected or any(
        len(q.options) != 4 or sum(o.is_correct for o in q.options) != 1 for q in questions
    ):
        raise ApiError(
            503,
            "question_bank_invalid",
            "The question bank for this quiz failed validation. Re-run the seed command.",
        )

    token = new_access_token()
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        access_token_hash=hash_token(token),
        mode=req.mode,
        week_no=req.week_no,
        study_mode=req.study_mode,
        status="in_progress",
        total_questions=len(questions),
    )
    for position, question in enumerate(fisher_yates(questions, rng), start=1):
        aq = AttemptQuestion(id=uuid.uuid4(), question_id=question.id, display_order=position)
        options = sorted(question.options, key=lambda o: str(o.source_label))
        for opt_pos, option in enumerate(fisher_yates(options, rng), start=1):
            aq.option_order.append(
                AttemptQuestionOption(option_id=option.id, question_id=question.id, display_order=opt_pos)
            )
        attempt.questions.append(aq)
    session.add(attempt)
    session.commit()
    logger.info(
        "attempt created id=%s mode=%s week=%s study=%s", attempt.id, attempt.mode, attempt.week_no, attempt.study_mode
    )
    return attempt, token


# ---- Access ------------------------------------------------------------------


def _attempt_query(attempt_id: uuid.UUID):
    return (
        select(QuizAttempt)
        .where(QuizAttempt.id == attempt_id)
        .options(
            selectinload(QuizAttempt.questions).selectinload(AttemptQuestion.question).selectinload(Question.options),
            selectinload(QuizAttempt.questions)
            .selectinload(AttemptQuestion.option_order)
            .selectinload(AttemptQuestionOption.option),
        )
        .execution_options(populate_existing=True)
    )


def authorize(session: Session, attempt_id: uuid.UUID, token: str | None, *, lock: bool = False) -> QuizAttempt:
    """Load an attempt the caller may access. Locks the attempt row when ``lock`` is set."""
    if not token:
        raise ApiError(401, "missing_token", "An attempt access token is required.")
    stmt = select(QuizAttempt).where(QuizAttempt.id == attempt_id).execution_options(populate_existing=True)
    if lock:
        stmt = stmt.with_for_update()
    attempt = session.scalars(stmt).first()
    if attempt is None:
        raise ApiError(404, "attempt_not_found", "This attempt does not exist.")
    if not token_matches(token, attempt.access_token_hash):
        raise ApiError(403, "invalid_token", "The access token is not valid for this attempt.")
    return attempt


def load_full_attempt(session: Session, attempt_id: uuid.UUID) -> QuizAttempt:
    attempt = session.scalars(_attempt_query(attempt_id)).first()
    assert attempt is not None
    return attempt


# ---- Serialisation -------------------------------------------------------------


def _correct_option_id(aq: AttemptQuestion) -> uuid.UUID:
    correct_ids = [o.id for o in aq.question.options if o.is_correct]
    if len(correct_ids) != 1:
        raise ApiError(503, "question_bank_invalid", "A question in this attempt has no single correct option.")
    return correct_ids[0]


def _study_feedback(attempt: QuizAttempt, aq: AttemptQuestion) -> schemas.StudyFeedback | None:
    """Correctness for an already-answered Study Mode question; never for Quiz Mode or unanswered questions."""
    if not attempt.study_mode or aq.selected_option_id is None:
        return None
    correct_id = _correct_option_id(aq)
    return schemas.StudyFeedback(is_correct=aq.selected_option_id == correct_id, correct_option_id=correct_id)


def to_active(attempt: QuizAttempt) -> schemas.AttemptOut:
    questions = [
        schemas.ActiveQuestion(
            attempt_question_id=aq.id,
            position=aq.display_order,
            question_text=aq.question.question_text,
            selected_option_id=aq.selected_option_id,
            feedback=_study_feedback(attempt, aq),
            options=[
                schemas.DisplayedOption(
                    id=aqo.option_id, label=LABELS[aqo.display_order - 1], text=aqo.option.option_text
                )
                for aqo in aq.option_order
            ],
        )
        for aq in attempt.questions
    ]
    return schemas.AttemptOut(
        id=attempt.id,
        mode=attempt.mode,
        week_no=attempt.week_no,
        title=quiz_title(attempt.mode, attempt.week_no),
        study_mode=attempt.study_mode,
        status=attempt.status,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        total_questions=attempt.total_questions,
        answered_count=sum(1 for aq in attempt.questions if aq.selected_option_id is not None),
        questions=questions,
    )


def to_result(attempt: QuizAttempt) -> schemas.AttemptResult:
    review = []
    correct_n = incorrect_n = unanswered_n = 0
    for aq in attempt.questions:
        correct = next(o for o in aq.question.options if o.is_correct)
        label_of = {aqo.option_id: LABELS[aqo.display_order - 1] for aqo in aq.option_order}
        selected = next((aqo.option for aqo in aq.option_order if aqo.option_id == aq.selected_option_id), None)
        if aq.selected_option_id is None:
            status = "unanswered"
            unanswered_n += 1
        elif aq.is_correct:
            status = "correct"
            correct_n += 1
        else:
            status = "incorrect"
            incorrect_n += 1
        review.append(
            schemas.ReviewItem(
                attempt_question_id=aq.id,
                position=aq.display_order,
                question_text=aq.question.question_text,
                status=status,
                selected_option_id=aq.selected_option_id,
                selected_option_text=selected.option_text if selected else None,
                selected_label=label_of.get(aq.selected_option_id) if selected else None,
                correct_option_id=correct.id,
                correct_option_text=correct.option_text,
                correct_label=label_of[correct.id],
                options=[
                    schemas.ReviewOption(
                        id=aqo.option_id,
                        label=LABELS[aqo.display_order - 1],
                        text=aqo.option.option_text,
                        is_correct=aqo.option_id == correct.id,
                        is_selected=aqo.option_id == aq.selected_option_id,
                    )
                    for aqo in aq.option_order
                ],
            )
        )
    return schemas.AttemptResult(
        attempt_id=attempt.id,
        mode=attempt.mode,
        week_no=attempt.week_no,
        title=quiz_title(attempt.mode, attempt.week_no),
        study_mode=attempt.study_mode,
        status="submitted",
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        total_questions=attempt.total_questions,
        correct_count=correct_n,
        incorrect_count=incorrect_n,
        unanswered_count=unanswered_n,
        score_correct=attempt.score_correct,
        score_percent=float(attempt.score_percent),
        review=review,
    )


# ---- Answers ---------------------------------------------------------------------


def save_answer(
    session: Session,
    attempt_id: uuid.UUID,
    token: str | None,
    attempt_question_id: uuid.UUID,
    option_id: uuid.UUID | None,
) -> schemas.AnswerSaved:
    # The row lock serialises saves with submission, so no answer can change after grading.
    attempt = authorize(session, attempt_id, token, lock=True)
    if attempt.status != "in_progress":
        raise ApiError(409, "attempt_not_in_progress", "This attempt has been submitted and can no longer be changed.")
    if attempt.study_mode:
        # Study Mode answers are locked once checked; they are recorded only via check_study_answer.
        raise ApiError(409, "study_mode_attempt", "Study Mode answers are checked with the study-answer endpoint.")
    aq = session.scalars(
        select(AttemptQuestion)
        .where(AttemptQuestion.id == attempt_question_id, AttemptQuestion.attempt_id == attempt.id)
        .options(selectinload(AttemptQuestion.option_order))
    ).first()
    if aq is None:
        raise ApiError(404, "question_not_in_attempt", "This question is not part of the attempt.")
    if option_id is not None and option_id not in {aqo.option_id for aqo in aq.option_order}:
        raise ApiError(422, "option_not_in_question", "The selected option does not belong to this question.")

    aq.selected_option_id = option_id
    aq.answered_at = datetime.now(UTC) if option_id is not None else None
    session.flush()
    answered = session.scalar(
        select(func.count())
        .select_from(AttemptQuestion)
        .where(AttemptQuestion.attempt_id == attempt.id, AttemptQuestion.selected_option_id.is_not(None))
    )
    session.commit()
    return schemas.AnswerSaved(
        attempt_question_id=aq.id,
        selected_option_id=aq.selected_option_id,
        answered_count=answered or 0,
        total_questions=attempt.total_questions,
        answered_at=aq.answered_at,
    )


def check_study_answer(
    session: Session,
    attempt_id: uuid.UUID,
    token: str | None,
    attempt_question_id: uuid.UUID,
    option_id: uuid.UUID,
) -> schemas.StudyAnswerChecked:
    """Record the first answer to a Study Mode question and reveal whether it was correct.

    The question locks after its first answer. Re-sending the same option returns the same
    result (safe network retries); choosing a different option is rejected.
    """
    attempt = authorize(session, attempt_id, token, lock=True)
    if not attempt.study_mode:
        raise ApiError(409, "not_study_mode", "Answers are revealed only in Study Mode attempts.")
    if attempt.status != "in_progress":
        raise ApiError(409, "attempt_not_in_progress", "This attempt has been submitted and can no longer be changed.")
    aq = session.scalars(
        select(AttemptQuestion)
        .where(AttemptQuestion.id == attempt_question_id, AttemptQuestion.attempt_id == attempt.id)
        .options(
            selectinload(AttemptQuestion.option_order),
            selectinload(AttemptQuestion.question).selectinload(Question.options),
        )
    ).first()
    if aq is None:
        raise ApiError(404, "question_not_in_attempt", "This question is not part of the attempt.")
    if option_id not in {aqo.option_id for aqo in aq.option_order}:
        raise ApiError(422, "option_not_in_question", "The selected option does not belong to this question.")
    if aq.selected_option_id is not None and aq.selected_option_id != option_id:
        raise ApiError(409, "question_locked", "This question has already been answered in Study Mode.")

    correct_id = _correct_option_id(aq)
    if aq.selected_option_id is None:
        aq.selected_option_id = option_id
        aq.answered_at = datetime.now(UTC)
        aq.is_correct = option_id == correct_id
        session.flush()
    answered, correct = session.execute(
        select(
            func.count(AttemptQuestion.selected_option_id),
            func.count().filter(AttemptQuestion.is_correct.is_(True)),
        ).where(AttemptQuestion.attempt_id == attempt.id)
    ).one()
    session.commit()
    return schemas.StudyAnswerChecked(
        attempt_question_id=aq.id,
        selected_option_id=option_id,
        is_correct=option_id == correct_id,
        correct_option_id=correct_id,
        answered_count=answered,
        correct_count=correct,
        total_questions=attempt.total_questions,
    )


# ---- Submission and grading ---------------------------------------------------------


def submit_attempt(session: Session, attempt_id: uuid.UUID, token: str | None) -> schemas.AttemptResult:
    """Grade and lock the attempt in one transaction; repeat calls return the stored result."""
    attempt = authorize(session, attempt_id, token, lock=True)
    if attempt.status == "submitted":
        session.commit()
        return to_result(load_full_attempt(session, attempt_id))
    if attempt.status != "in_progress":
        raise ApiError(409, "attempt_not_in_progress", "This attempt can no longer be submitted.")

    full = load_full_attempt(session, attempt_id)
    correct_n = 0
    for aq in full.questions:
        correct_ids = [o.id for o in aq.question.options if o.is_correct]
        if len(correct_ids) != 1:
            raise ApiError(503, "question_bank_invalid", "A question in this attempt has no single correct option.")
        aq.is_correct = aq.selected_option_id is not None and aq.selected_option_id == correct_ids[0]
        correct_n += aq.is_correct
    full.score_correct = correct_n
    full.score_percent = percent(correct_n, full.total_questions)
    full.status = "submitted"
    full.submitted_at = datetime.now(UTC)
    session.commit()
    logger.info("attempt submitted id=%s score=%s/%s", full.id, correct_n, full.total_questions)
    return to_result(full)


def get_result(session: Session, attempt_id: uuid.UUID, token: str | None) -> schemas.AttemptResult:
    attempt = authorize(session, attempt_id, token)
    if attempt.status != "submitted":
        raise ApiError(409, "attempt_not_submitted", "Results are available only after the attempt is submitted.")
    return to_result(load_full_attempt(session, attempt_id))
