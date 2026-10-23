import type {
  AnswerSaved,
  Attempt,
  AttemptResult,
  CreatedAttempt,
  QuizCatalogue,
  QuizMode,
  StudyAnswerChecked,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "") + "/api/v1";

/** An error returned by the API ({"error": {code, message}}) or a network failure (status 0). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }

  /** The attempt cannot be opened with the credentials this browser holds. */
  get isAccessProblem(): boolean {
    return this.status === 401 || this.status === 403 || this.status === 404;
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the server. Check your connection and try again.");
  }
  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new ApiError(response.status, code, message);
  }
  return (await response.json()) as T;
}

export const api = {
  getCatalogue: () => request<QuizCatalogue>("/quizzes"),

  createAttempt: (mode: QuizMode, weekNo?: number | null, studyMode = false) =>
    request<CreatedAttempt>("/attempts", {
      method: "POST",
      body: JSON.stringify({
        ...(mode === "weekly" ? { mode, week_no: weekNo } : { mode }),
        ...(studyMode ? { study_mode: true } : {}),
      }),
    }),

  getAttempt: (attemptId: string, token: string) => request<Attempt>(`/attempts/${attemptId}`, {}, token),

  saveAnswer: (attemptId: string, attemptQuestionId: string, optionId: string | null, token: string) =>
    request<AnswerSaved>(
      `/attempts/${attemptId}/questions/${attemptQuestionId}/answer`,
      { method: "PUT", body: JSON.stringify({ selected_option_id: optionId }) },
      token,
    ),

  /** Study Mode: lock in an answer and learn whether it is correct. */
  checkStudyAnswer: (attemptId: string, attemptQuestionId: string, optionId: string, token: string) =>
    request<StudyAnswerChecked>(
      `/attempts/${attemptId}/questions/${attemptQuestionId}/study-answer`,
      { method: "POST", body: JSON.stringify({ selected_option_id: optionId }) },
      token,
    ),

  submitAttempt: (attemptId: string, token: string) =>
    request<AttemptResult>(`/attempts/${attemptId}/submit`, { method: "POST" }, token),

  getResult: (attemptId: string, token: string) => request<AttemptResult>(`/attempts/${attemptId}/result`, {}, token),
};
