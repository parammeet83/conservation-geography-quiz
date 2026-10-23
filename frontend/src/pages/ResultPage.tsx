import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { AttemptResult, ReviewItem, ReviewStatus } from "../api/types";
import { attemptStore } from "../lib/attemptStore";
import { startAttempt } from "../lib/startAttempt";

type Filter = "all" | ReviewStatus;

const STATUS_TEXT: Record<ReviewStatus, { icon: string; label: string }> = {
  correct: { icon: "✓", label: "Correct" },
  incorrect: { icon: "✗", label: "Incorrect" },
  unanswered: { icon: "–", label: "Unanswered" },
};

export default function ResultPage() {
  const { attemptId = "" } = useParams();
  const navigate = useNavigate();
  const token = useMemo(() => attemptStore.get(attemptId)?.token ?? null, [attemptId]);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<{ message: string; access: boolean } | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) {
      setError({ message: "The access key for this attempt is not stored in this browser.", access: true });
      return;
    }
    setError(null);
    try {
      setResult(await api.getResult(attemptId, token));
      attemptStore.markSubmitted(attemptId);
    } catch (err) {
      if (err instanceof ApiError && err.code === "attempt_not_submitted") {
        navigate(`/attempts/${attemptId}`, { replace: true });
        return;
      }
      setError({
        message: err instanceof Error ? err.message : "Could not load the results.",
        access: err instanceof ApiError && err.isAccessProblem,
      });
    }
  }, [attemptId, token, navigate]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  useEffect(() => {
    if (result) document.title = `Results · ${result.title}`;
  }, [result]);

  async function tryAgain() {
    if (!result) return;
    setRestarting(true);
    setRestartError(null);
    try {
      const id = await startAttempt(result.mode, result.week_no, result.study_mode);
      navigate(`/attempts/${id}`);
    } catch (err) {
      setRestartError(err instanceof Error ? err.message : "Could not start a new attempt.");
      setRestarting(false);
    }
  }

  if (error) {
    return (
      <section className="panel" role="alert">
        <h1>{error.access ? "These results can't be opened" : "Could not load the results"}</h1>
        <p>{error.message}</p>
        <div className="button-row">
          {!error.access && (
            <button type="button" className="btn btn--primary" onClick={() => void load()}>
              Retry
            </button>
          )}
          <Link className="btn btn--secondary" to="/">
            Back to quiz selection
          </Link>
        </div>
      </section>
    );
  }
  if (!result) {
    return (
      <p className="status-line" role="status">
        Loading results…
      </p>
    );
  }

  const visible = filter === "all" ? result.review : result.review.filter((r) => r.status === filter);
  const counts: Record<Filter, number> = {
    all: result.total_questions,
    correct: result.correct_count,
    incorrect: result.incorrect_count,
    unanswered: result.unanswered_count,
  };

  return (
    <div className="results">
      <p className="quiz-header__scope">
        {result.title} · {result.mode === "overall" ? "All weeks" : "Weekly quiz"}
        {result.study_mode ? " · Study Mode" : ""}
      </p>
      <h1 className="page-title">{result.study_mode ? "Study session summary" : "Your results"}</h1>

      <section className="score-card" aria-labelledby="score-heading">
        <h2 id="score-heading" className="visually-hidden">
          Score summary
        </h2>
        <p className="score-card__main">
          <span className="score-card__score" data-testid="score">
            {result.score_correct} / {result.total_questions}
          </span>
          <span className="score-card__percent" data-testid="percent">
            {result.score_percent.toFixed(2)}%
          </span>
        </p>
        <dl className="score-card__breakdown">
          <div>
            <dt>Total questions</dt>
            <dd>{result.total_questions}</dd>
          </div>
          <div>
            <dt>Correct</dt>
            <dd data-testid="count-correct">{result.correct_count}</dd>
          </div>
          <div>
            <dt>Incorrect</dt>
            <dd data-testid="count-incorrect">{result.incorrect_count}</dd>
          </div>
          <div>
            <dt>Unanswered</dt>
            <dd data-testid="count-unanswered">{result.unanswered_count}</dd>
          </div>
        </dl>
        <p className="hint">One point per correct answer. Incorrect and unanswered questions score zero.</p>
        <div className="button-row">
          <button type="button" className="btn btn--primary" onClick={() => void tryAgain()} disabled={restarting}>
            {restarting ? "Starting…" : "Try again"}
          </button>
          <Link className="btn btn--secondary" to="/">
            Back to quiz selection
          </Link>
        </div>
        {restartError && (
          <p className="alert alert--error" role="alert">
            {restartError}
          </p>
        )}
      </section>

      <section aria-labelledby="review-heading">
        <h2 id="review-heading" className="section-title">
          Answer review
        </h2>
        <div className="filter-bar" role="group" aria-label="Filter questions">
          {(["all", "incorrect", "unanswered", "correct"] as Filter[]).map((f) => (
            <button
              key={f}
              type="button"
              className={`chip${filter === f ? " chip--active" : ""}`}
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? "All" : STATUS_TEXT[f].label} ({counts[f]})
            </button>
          ))}
        </div>

        {result.total_questions > 10 && visible.length > 0 && (
          <nav aria-label="Jump to question" className="jump-links">
            {visible.map((r) => (
              <a key={r.attempt_question_id} href={`#review-${r.position}`} className={`jump jump--${r.status}`}>
                <span className="visually-hidden">
                  Question {r.position}, {STATUS_TEXT[r.status].label}
                </span>
                <span aria-hidden="true">{r.position}</span>
              </a>
            ))}
          </nav>
        )}

        {visible.length === 0 && <p className="hint">No questions in this category.</p>}
        <ol className="review-list">
          {visible.map((item) => (
            <ReviewCard key={item.attempt_question_id} item={item} />
          ))}
        </ol>
      </section>
    </div>
  );
}

function ReviewCard({ item }: { item: ReviewItem }) {
  const s = STATUS_TEXT[item.status];
  return (
    <li id={`review-${item.position}`} className={`review review--${item.status}`} data-testid="review-item">
      <div className="review__head">
        <h3 className="review__number">Question {item.position}</h3>
        <span className={`badge badge--${item.status}`}>
          <span aria-hidden="true">{s.icon}</span>
          {s.label}
        </span>
      </div>
      <p className="review__question">{item.question_text}</p>
      <dl className="review__answers">
        <div>
          <dt>Your answer</dt>
          <dd>
            {item.selected_option_text != null ? (
              <>
                <strong>{item.selected_label}.</strong> {item.selected_option_text}
              </>
            ) : (
              <em>Not answered</em>
            )}
          </dd>
        </div>
        <div>
          <dt>Correct answer</dt>
          <dd>
            <strong>{item.correct_label}.</strong> {item.correct_option_text}
          </dd>
        </div>
      </dl>
      <details className="review__options">
        <summary>Show all options</summary>
        <ul>
          {item.options.map((o) => (
            <li key={o.id} className={o.is_correct ? "is-correct" : o.is_selected ? "is-wrong" : ""}>
              <strong>{o.label}.</strong> {o.text}
              {o.is_correct && <span className="tag"> ✓ Correct answer</span>}
              {o.is_selected && <span className="tag"> ● Your answer</span>}
            </li>
          ))}
        </ul>
      </details>
    </li>
  );
}
