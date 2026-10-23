"""Pydantic request/response models.

Active-attempt models deliberately have no correctness fields at any depth;
correct-answer data exists only in the result models, which are served after
submission.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Mode = Literal["weekly", "overall"]
AttemptStatus = Literal["in_progress", "submitted", "abandoned"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- Catalogue -------------------------------------------------------------


class WeekQuiz(BaseModel):
    week_no: int
    title: str
    question_count: int
    available: bool


class OverallQuiz(BaseModel):
    title: str
    question_count: int
    available: bool


class QuizCatalogue(BaseModel):
    weeks: list[WeekQuiz]
    overall: OverallQuiz


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


# ---- Attempt creation and active attempt ----------------------------------


class CreateAttemptRequest(StrictModel):
    mode: Mode
    week_no: int | None = None
    # Study Mode: correctness of each answer is revealed immediately and the question locks.
    study_mode: bool = False

    @model_validator(mode="after")
    def check_week(self) -> "CreateAttemptRequest":
        if self.mode == "weekly":
            if self.week_no is None or not 1 <= self.week_no <= 12:
                raise ValueError("weekly mode requires week_no between 1 and 12")
        elif self.week_no is not None:
            raise ValueError("overall mode must not include week_no")
        return self


class DisplayedOption(BaseModel):
    id: uuid.UUID
    label: str
    text: str


class StudyFeedback(BaseModel):
    """Revealed only in Study Mode, and only for a question that has already been answered."""

    is_correct: bool
    correct_option_id: uuid.UUID


class ActiveQuestion(BaseModel):
    attempt_question_id: uuid.UUID
    position: int
    question_text: str
    options: list[DisplayedOption]
    selected_option_id: uuid.UUID | None
    feedback: StudyFeedback | None = None


class AttemptOut(BaseModel):
    id: uuid.UUID
    mode: Mode
    week_no: int | None
    title: str
    study_mode: bool
    status: AttemptStatus
    started_at: datetime
    submitted_at: datetime | None
    total_questions: int
    answered_count: int
    questions: list[ActiveQuestion]


class CreatedAttemptOut(AttemptOut):
    access_token: str


class AnswerUpdate(StrictModel):
    selected_option_id: uuid.UUID | None


class AnswerSaved(BaseModel):
    attempt_question_id: uuid.UUID
    selected_option_id: uuid.UUID | None
    answered_count: int
    total_questions: int
    answered_at: datetime | None


class StudyAnswerRequest(StrictModel):
    selected_option_id: uuid.UUID


class StudyAnswerChecked(BaseModel):
    attempt_question_id: uuid.UUID
    selected_option_id: uuid.UUID
    is_correct: bool
    correct_option_id: uuid.UUID
    answered_count: int
    correct_count: int
    total_questions: int


# ---- Results (only after submission) --------------------------------------


class ReviewOption(BaseModel):
    id: uuid.UUID
    label: str
    text: str
    is_correct: bool
    is_selected: bool


class ReviewItem(BaseModel):
    attempt_question_id: uuid.UUID
    position: int
    question_text: str
    status: Literal["correct", "incorrect", "unanswered"]
    selected_option_id: uuid.UUID | None
    selected_option_text: str | None
    selected_label: str | None
    correct_option_id: uuid.UUID
    correct_option_text: str
    correct_label: str
    options: list[ReviewOption]


class AttemptResult(BaseModel):
    attempt_id: uuid.UUID
    mode: Mode
    week_no: int | None
    title: str
    study_mode: bool
    status: Literal["submitted"]
    started_at: datetime
    submitted_at: datetime
    total_questions: int
    correct_count: int
    incorrect_count: int
    unanswered_count: int
    score_correct: int
    score_percent: float
    review: list[ReviewItem]
