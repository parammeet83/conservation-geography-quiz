"""HTTP routes under /api/v1."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.errors import ApiError
from app.services import quiz
from app.shuffle import RandomSource, SecureRandom

router = APIRouter(prefix="/api/v1")

SessionDep = Annotated[Session, Depends(get_session)]


def get_rng() -> RandomSource:
    """Random source for shuffles; tests override this dependency."""
    return SecureRandom()


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


TokenDep = Annotated[str | None, Depends(bearer_token)]


@router.get("/health", response_model=schemas.Health)
def health(session: SessionDep, response: Response) -> schemas.Health:
    try:
        session.execute(text("SELECT 1"))
        return schemas.Health(status="ok", database="ok")
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return schemas.Health(status="degraded", database="unavailable")


@router.get("/quizzes", response_model=schemas.QuizCatalogue)
def list_quizzes(session: SessionDep) -> schemas.QuizCatalogue:
    return quiz.get_catalogue(session)


@router.post("/attempts", response_model=schemas.CreatedAttemptOut, status_code=status.HTTP_201_CREATED)
def create_attempt(
    req: schemas.CreateAttemptRequest,
    session: SessionDep,
    rng: Annotated[RandomSource, Depends(get_rng)],
    response: Response,
) -> schemas.CreatedAttemptOut:
    attempt, token = quiz.create_attempt(session, req, rng)
    response.headers["Cache-Control"] = "no-store"
    active = quiz.to_active(quiz.load_full_attempt(session, attempt.id))
    return schemas.CreatedAttemptOut(**active.model_dump(), access_token=token)


@router.get("/attempts/{attempt_id}", response_model=schemas.AttemptOut)
def get_attempt(attempt_id: uuid.UUID, session: SessionDep, token: TokenDep) -> schemas.AttemptOut:
    attempt = quiz.authorize(session, attempt_id, token)
    return quiz.to_active(quiz.load_full_attempt(session, attempt.id))


@router.put(
    "/attempts/{attempt_id}/questions/{attempt_question_id}/answer",
    response_model=schemas.AnswerSaved,
)
def save_answer(
    attempt_id: uuid.UUID,
    attempt_question_id: uuid.UUID,
    body: schemas.AnswerUpdate,
    session: SessionDep,
    token: TokenDep,
) -> schemas.AnswerSaved:
    return quiz.save_answer(session, attempt_id, token, attempt_question_id, body.selected_option_id)


@router.post(
    "/attempts/{attempt_id}/questions/{attempt_question_id}/study-answer",
    response_model=schemas.StudyAnswerChecked,
)
def check_study_answer(
    attempt_id: uuid.UUID,
    attempt_question_id: uuid.UUID,
    body: schemas.StudyAnswerRequest,
    session: SessionDep,
    token: TokenDep,
) -> schemas.StudyAnswerChecked:
    """Study Mode only: lock in an answer and reveal whether it is correct."""
    return quiz.check_study_answer(session, attempt_id, token, attempt_question_id, body.selected_option_id)


@router.post("/attempts/{attempt_id}/submit", response_model=schemas.AttemptResult)
def submit_attempt(
    attempt_id: uuid.UUID,
    session: SessionDep,
    token: TokenDep,
    body: Annotated[dict[str, Any] | None, Body()] = None,
) -> schemas.AttemptResult:
    # Scores are computed on the server only; any client-supplied fields are rejected.
    if body:
        raise ApiError(
            422,
            "unexpected_fields",
            "Submission does not accept a request body.",
            details=sorted(body.keys()),
        )
    return quiz.submit_attempt(session, attempt_id, token)


@router.get("/attempts/{attempt_id}/result", response_model=schemas.AttemptResult)
def get_result(attempt_id: uuid.UUID, session: SessionDep, token: TokenDep) -> schemas.AttemptResult:
    return quiz.get_result(session, attempt_id, token)
