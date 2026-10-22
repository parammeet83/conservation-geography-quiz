import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { QuizCatalogue, QuizMode } from "../api/types";
import { attemptStore } from "../lib/attemptStore";
import { startAttempt } from "../lib/startAttempt";

type Scope = { mode: QuizMode; weekNo: number | null };
const scopeKey = (s: Scope) => (s.mode === "overall" ? "overall" : `week-${s.weekNo}`);

export default function HomePage() {
  const navigate = useNavigate();
  const [catalogue, setCatalogue] = useState<QuizCatalogue | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    setCatalogue(null);
    try {
      setCatalogue(await api.getCatalogue());
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Could not load the quiz list.");
    }
  }, []);

  useEffect(() => {
    document.title = "Conservation Geography Quiz";
    // Fetching on mount; state updates happen after the request resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function begin(scope: Scope) {
    setStarting(scopeKey(scope));
    setStartError(null);
    try {
      const id = await startAttempt(scope.mode, scope.weekNo);
      navigate(`/attempts/${id}`);
    } catch (err) {
      setStartError(err instanceof ApiError ? err.message : "Could not start the quiz. Please try again.");
      setStarting(null);
    }
  }

  return (
    <div className="home">
      <h1 className="page-title">Conservation Geography Quiz</h1>
      <p className="lede">Choose a week to practice or take the full 120-question test.</p>
      <p className="hint">
        Questions and answer options are shuffled for every new attempt. Your answers are saved as you go, and the
        correct answers are shown after you submit.
      </p>

      {startError && (
        <div className="alert alert--error" role="alert">
          {startError}
        </div>
      )}

      {!catalogue && !loadError && (
        <p className="status-line" role="status">
          Loading quizzes…
        </p>
      )}

      {loadError && (
        <div className="alert alert--error" role="alert">
          <p>{loadError}</p>
          <button type="button" className="btn btn--secondary" onClick={() => void load()}>
            Retry
          </button>
        </div>
      )}

      {catalogue && (
        <>
          <section aria-labelledby="overall-heading" className="overall-section">
            <QuizCard
              headingId="overall-heading"
              title={catalogue.overall.title}
              description="All weeks combined"
              count={catalogue.overall.question_count}
              available={catalogue.overall.available}
              scope={{ mode: "overall", weekNo: null }}
              starting={starting}
              onStart={begin}
              featured
            />
          </section>

          <section aria-labelledby="weeks-heading">
            <h2 id="weeks-heading" className="section-title">
              Weekly quizzes
            </h2>
            <ul className="week-grid">
              {catalogue.weeks.map((w) => (
                <li key={w.week_no}>
                  <QuizCard
                    title={w.title}
                    count={w.question_count}
                    available={w.available}
                    scope={{ mode: "weekly", weekNo: w.week_no }}
                    starting={starting}
                    onStart={begin}
                  />
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

interface QuizCardProps {
  title: string;
  description?: string;
  count: number;
  available: boolean;
  scope: Scope;
  starting: string | null;
  onStart: (scope: Scope) => void;
  featured?: boolean;
  headingId?: string;
}

function QuizCard({ title, description, count, available, scope, starting, onStart, featured, headingId }: QuizCardProps) {
  const key = scopeKey(scope);
  const isStarting = starting === key;
  const resume = attemptStore.inProgressFor(scope.mode, scope.weekNo);
  const countText = `${count} ${count === 1 ? "question" : "questions"}`;

  return (
    <article className={`quiz-card${featured ? " quiz-card--featured" : ""}`}>
      <div className="quiz-card__body">
        <h3 id={headingId} className="quiz-card__title">
          {title}
        </h3>
        {description && <p className="quiz-card__desc">{description}</p>}
        <p className="quiz-card__count">{countText}</p>
        {!available && <p className="quiz-card__unavailable">Unavailable: question bank incomplete</p>}
      </div>
      <div className="quiz-card__actions">
        {resume && (
          <Link className="btn btn--secondary" to={`/attempts/${resume.attemptId}`}>
            Resume <span className="visually-hidden">{title}</span>
          </Link>
        )}
        <button
          type="button"
          className="btn btn--primary"
          disabled={!available || starting !== null}
          onClick={() => onStart(scope)}
          aria-label={`${resume ? "Start a new attempt of" : "Start"} ${title}, ${countText}`}
        >
          {isStarting ? "Starting…" : resume ? "Start new" : "Start"}
        </button>
      </div>
    </article>
  );
}
