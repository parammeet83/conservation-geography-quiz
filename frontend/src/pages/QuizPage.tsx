import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Attempt } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import QuestionPalette from "../components/QuestionPalette";
import { attemptStore } from "../lib/attemptStore";

export type SaveStatus = "saving" | "saved" | "error";

type Phase =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "access_error" }
  | { kind: "load_error"; message: string };

export default function QuizPage() {
  const { attemptId = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const stored = useMemo(() => attemptStore.get(attemptId), [attemptId]);
  const token = stored?.token ?? null;

  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [selections, setSelections] = useState<Record<string, string | null>>({});
  const [saveStatus, setSaveStatus] = useState<Record<string, SaveStatus>>({});
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});
  const [dialogOpen, setDialogOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const requestSeq = useRef<Record<string, number>>({});
  const headingRef = useRef<HTMLHeadingElement>(null);
  const moveFocus = useRef(false);
  // The navigator starts expanded on wide screens and for short quizzes; collapsible on phones.
  const wideScreen = useMemo(() => window.matchMedia?.("(min-width: 901px)")?.matches ?? true, []);

  const total = attempt?.questions.length ?? 0;
  const requested = Number(searchParams.get("q") ?? "1");
  const currentIndex = Number.isInteger(requested) && requested >= 1 && requested <= total ? requested - 1 : 0;
  const question = attempt?.questions[currentIndex];

  // ---- loading --------------------------------------------------------------------------
  const load = useCallback(async () => {
    if (!token) {
      setPhase({ kind: "access_error" });
      return;
    }
    setPhase({ kind: "loading" });
    try {
      const data = await api.getAttempt(attemptId, token);
      if (data.status === "submitted") {
        attemptStore.markSubmitted(attemptId);
        navigate(`/attempts/${attemptId}/result`, { replace: true });
        return;
      }
      setAttempt(data);
      setSelections(Object.fromEntries(data.questions.map((q) => [q.attempt_question_id, q.selected_option_id])));
      setSaveStatus({});
      setPhase({ kind: "ready" });
    } catch (err) {
      if (err instanceof ApiError && err.isAccessProblem) setPhase({ kind: "access_error" });
      else setPhase({ kind: "load_error", message: err instanceof Error ? err.message : "Could not load the quiz." });
    }
  }, [attemptId, token, navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (attempt) document.title = `${attempt.title} · Question ${currentIndex + 1} of ${total}`;
  }, [attempt, currentIndex, total]);

  useEffect(() => {
    if (moveFocus.current) {
      headingRef.current?.focus();
      moveFocus.current = false;
    }
  }, [currentIndex]);

  // ---- saving -----------------------------------------------------------------------------
  const pendingIds = Object.keys(saveStatus).filter((id) => saveStatus[id] !== "saved");
  const failedIds = pendingIds.filter((id) => saveStatus[id] === "error");
  const savingCount = pendingIds.length - failedIds.length;

  useEffect(() => {
    if (pendingIds.length === 0) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [pendingIds.length]);

  const persist = useCallback(
    async (aqId: string, optionId: string | null) => {
      if (!token) return;
      const seq = (requestSeq.current[aqId] ?? 0) + 1;
      requestSeq.current[aqId] = seq;
      setSaveStatus((s) => ({ ...s, [aqId]: "saving" }));
      try {
        await api.saveAnswer(attemptId, aqId, optionId, token);
        // Ignore responses that were overtaken by a newer selection for the same question.
        if (requestSeq.current[aqId] === seq) setSaveStatus((s) => ({ ...s, [aqId]: "saved" }));
      } catch (err) {
        if (requestSeq.current[aqId] !== seq) return;
        if (err instanceof ApiError && err.code === "attempt_not_in_progress") {
          attemptStore.markSubmitted(attemptId);
          navigate(`/attempts/${attemptId}/result`, { replace: true });
          return;
        }
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          setPhase({ kind: "access_error" });
          return;
        }
        setSaveStatus((s) => ({ ...s, [aqId]: "error" }));
        setSaveErrors((m) => ({ ...m, [aqId]: err instanceof Error ? err.message : "Save failed." }));
      }
    },
    [attemptId, token, navigate],
  );

  function select(aqId: string, optionId: string | null) {
    setSelections((s) => ({ ...s, [aqId]: optionId }));
    void persist(aqId, optionId);
  }

  function retryFailed() {
    for (const id of failedIds) void persist(id, selections[id] ?? null);
  }

  // ---- navigation ---------------------------------------------------------------------------
  function goTo(index: number) {
    moveFocus.current = true;
    setSearchParams({ q: String(index + 1) }, { replace: true });
  }

  // ---- submission -----------------------------------------------------------------------------
  async function submit() {
    if (!token || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.submitAttempt(attemptId, token);
    } catch (err) {
      // Submission is idempotent: if the response was lost, the attempt may already be graded.
      try {
        await api.getResult(attemptId, token);
      } catch {
        setSubmitError(err instanceof Error ? err.message : "Submission failed. Please try again.");
        setSubmitting(false);
        return;
      }
    }
    attemptStore.markSubmitted(attemptId);
    navigate(`/attempts/${attemptId}/result`, { replace: true });
  }

  // ---- render ------------------------------------------------------------------------------------
  if (phase.kind === "access_error") {
    return (
      <section className="panel" role="alert">
        <h1>This attempt can't be opened</h1>
        <p>
          The access key for this quiz attempt is missing or no longer valid in this browser. Attempts can only be
          resumed in the browser where they were started. A new attempt has <strong>not</strong> been created.
        </p>
        <Link className="btn btn--primary" to="/">
          Back to quiz selection
        </Link>
      </section>
    );
  }
  if (phase.kind === "load_error") {
    return (
      <section className="panel" role="alert">
        <h1>Could not load the quiz</h1>
        <p>{phase.message}</p>
        <div className="button-row">
          <button type="button" className="btn btn--primary" onClick={() => void load()}>
            Retry
          </button>
          <Link className="btn btn--secondary" to="/">
            Back to quiz selection
          </Link>
        </div>
      </section>
    );
  }
  if (phase.kind === "loading" || !attempt || !question) {
    return (
      <p className="status-line" role="status">
        Loading quiz…
      </p>
    );
  }

  const answered = Object.values(selections).filter((v) => v != null).length;
  const unanswered = total - answered;
  const selected = selections[question.attempt_question_id] ?? null;
  const currentStatus = saveStatus[question.attempt_question_id];
  const progressPct = Math.round((answered / total) * 100);

  return (
    <div className="quiz">
      <header className="quiz-header">
        <p className="quiz-header__scope">
          {attempt.title}
          <span className="quiz-header__mode">{attempt.mode === "overall" ? " · All weeks" : ""}</span>
        </p>
        <h1 className="quiz-header__position" ref={headingRef} tabIndex={-1}>
          Question {currentIndex + 1} of {total}
        </h1>
        <div className="progress">
          <div
            className="progress__track"
            role="progressbar"
            aria-label="Questions answered"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={answered}
            aria-valuetext={`${answered} of ${total} answered`}
          >
            <div className="progress__fill" style={{ width: `${progressPct}%` }} />
          </div>
          <p className="progress__text" data-testid="progress-text">
            {answered} answered · {unanswered} remaining
          </p>
        </div>
      </header>

      <div className="quiz-layout">
        <div className="quiz-main">
          <fieldset className="question" key={question.attempt_question_id}>
            <legend className="question__text">{question.question_text}</legend>
            <div className="options">
              {question.options.map((opt) => (
                <label key={opt.id} className={`option${selected === opt.id ? " option--selected" : ""}`}>
                  <input
                    type="radio"
                    name={`q-${question.attempt_question_id}`}
                    value={opt.id}
                    checked={selected === opt.id}
                    onChange={() => select(question.attempt_question_id, opt.id)}
                  />
                  <span className="option__label" aria-hidden="true">
                    {opt.label}
                  </span>
                  <span className="option__text">
                    <span className="visually-hidden">Option {opt.label}: </span>
                    {opt.text}
                  </span>
                </label>
              ))}
            </div>
            <div className="question__footer">
              <SaveIndicator
                status={currentStatus}
                hasAnswer={selected != null}
                error={saveErrors[question.attempt_question_id]}
                onRetry={() => void persist(question.attempt_question_id, selected)}
              />
              {selected != null && (
                <button
                  type="button"
                  className="btn btn--link"
                  onClick={() => select(question.attempt_question_id, null)}
                >
                  Clear selection
                </button>
              )}
            </div>
          </fieldset>

          <div className="quiz-nav">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => goTo(currentIndex - 1)}
              disabled={currentIndex === 0}
            >
              ← Previous
            </button>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => goTo(currentIndex + 1)}
              disabled={currentIndex === total - 1}
            >
              Next →
            </button>
          </div>

          {failedIds.length > 0 && (
            <div className="alert alert--error" role="alert">
              <p>
                {failedIds.length} {failedIds.length === 1 ? "answer has" : "answers have"} not been saved. Your
                selections are kept on this page.
              </p>
              <button type="button" className="btn btn--secondary" onClick={retryFailed}>
                Retry saving
              </button>
            </div>
          )}
        </div>

        <aside className="quiz-side" aria-label="Quiz progress and submission">
          <details className="palette-panel" open={wideScreen || total <= 10 ? true : undefined}>
            <summary>Go to question</summary>
            <QuestionPalette
              questionIds={attempt.questions.map((q) => q.attempt_question_id)}
              currentIndex={currentIndex}
              selections={selections}
              saveStatus={saveStatus}
              onJump={goTo}
            />
            <p className="palette-legend">
              <span className="legend-item">
                <span className="legend-swatch legend-swatch--answered" aria-hidden="true">
                  ✓
                </span>
                Answered
              </span>
              <span className="legend-item">
                <span className="legend-swatch" aria-hidden="true" />
                Unanswered
              </span>
              <span className="legend-item">
                <span className="legend-swatch legend-swatch--current" aria-hidden="true" />
                Current
              </span>
            </p>
          </details>
          <p className="sr-status" role="status" aria-live="polite">
            {savingCount > 0
              ? "Saving…"
              : failedIds.length > 0
                ? `${failedIds.length} not saved`
                : Object.keys(saveStatus).length > 0
                  ? "All answers saved"
                  : ""}
          </p>
          <button type="button" className="btn btn--primary btn--block" onClick={() => setDialogOpen(true)}>
            Submit quiz
          </button>
        </aside>
      </div>

      {dialogOpen && (
        <ConfirmDialog title="Submit this quiz?" onClose={() => setDialogOpen(false)} busy={submitting}>
          <dl className="dialog__counts">
            <div>
              <dt>Answered</dt>
              <dd data-testid="dialog-answered">{answered}</dd>
            </div>
            <div>
              <dt>Unanswered</dt>
              <dd data-testid="dialog-unanswered">{unanswered}</dd>
            </div>
          </dl>
          {unanswered > 0 && (
            <p className="alert alert--warning">
              You have {unanswered} unanswered {unanswered === 1 ? "question" : "questions"}. Submit anyway?
              Unanswered questions score zero.
            </p>
          )}
          {pendingIds.length > 0 && (
            <div className="alert alert--error" role="alert">
              <p>
                {failedIds.length > 0
                  ? `${failedIds.length} ${failedIds.length === 1 ? "answer is" : "answers are"} not saved yet. Retry saving before submitting so they are graded.`
                  : "Some answers are still saving. Please wait a moment."}
              </p>
              {failedIds.length > 0 && (
                <button type="button" className="btn btn--secondary" onClick={retryFailed}>
                  Retry saving
                </button>
              )}
            </div>
          )}
          <p>Submission is final for this attempt. Correct answers are shown after you submit.</p>
          {submitError && (
            <p className="alert alert--error" role="alert">
              {submitError}
            </p>
          )}
          <div className="button-row">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setDialogOpen(false)}
              disabled={submitting}
            >
              Review answers
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void submit()}
              disabled={submitting || pendingIds.length > 0}
            >
              {submitting ? "Submitting…" : "Submit quiz"}
            </button>
          </div>
        </ConfirmDialog>
      )}
    </div>
  );
}

function SaveIndicator({
  status,
  hasAnswer,
  error,
  onRetry,
}: {
  status: SaveStatus | undefined;
  hasAnswer: boolean;
  error?: string;
  onRetry: () => void;
}) {
  if (status === "saving") return <span className="save save--saving">Saving…</span>;
  if (status === "error")
    return (
      <span className="save save--error">
        <span aria-hidden="true">⚠ </span>Not saved{error ? ` (${error})` : ""}.{" "}
        <button type="button" className="btn btn--link" onClick={onRetry}>
          Retry
        </button>
      </span>
    );
  if (status === "saved") return <span className="save save--saved">✓ {hasAnswer ? "Answer saved" : "Cleared"}</span>;
  return hasAnswer ? <span className="save save--saved">✓ Answer saved</span> : <span className="save" />;
}
