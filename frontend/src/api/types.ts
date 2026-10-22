// Types mirror the FastAPI response models in backend/app/schemas.py.
// Active-attempt types intentionally carry no correctness information.

export type QuizMode = "weekly" | "overall";
export type AttemptStatus = "in_progress" | "submitted" | "abandoned";

export interface WeekQuiz {
  week_no: number;
  title: string;
  question_count: number;
  available: boolean;
}

export interface QuizCatalogue {
  weeks: WeekQuiz[];
  overall: { title: string; question_count: number; available: boolean };
}

export interface DisplayedOption {
  id: string;
  label: string;
  text: string;
}

export interface AttemptQuestion {
  attempt_question_id: string;
  position: number;
  question_text: string;
  options: DisplayedOption[];
  selected_option_id: string | null;
}

export interface Attempt {
  id: string;
  mode: QuizMode;
  week_no: number | null;
  title: string;
  status: AttemptStatus;
  started_at: string;
  submitted_at: string | null;
  total_questions: number;
  answered_count: number;
  questions: AttemptQuestion[];
}

export interface CreatedAttempt extends Attempt {
  access_token: string;
}

export interface AnswerSaved {
  attempt_question_id: string;
  selected_option_id: string | null;
  answered_count: number;
  total_questions: number;
  answered_at: string | null;
}

export type ReviewStatus = "correct" | "incorrect" | "unanswered";

export interface ReviewOption {
  id: string;
  label: string;
  text: string;
  is_correct: boolean;
  is_selected: boolean;
}

export interface ReviewItem {
  attempt_question_id: string;
  position: number;
  question_text: string;
  status: ReviewStatus;
  selected_option_id: string | null;
  selected_option_text: string | null;
  selected_label: string | null;
  correct_option_id: string;
  correct_option_text: string;
  correct_label: string;
  options: ReviewOption[];
}

export interface AttemptResult {
  attempt_id: string;
  mode: QuizMode;
  week_no: number | null;
  title: string;
  status: "submitted";
  started_at: string;
  submitted_at: string;
  total_questions: number;
  correct_count: number;
  incorrect_count: number;
  unanswered_count: number;
  score_correct: number;
  score_percent: number;
  review: ReviewItem[];
}
