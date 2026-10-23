import type { StudyFeedback } from "../api/types";
import type { SaveStatus } from "../pages/QuizPage";

interface Props {
  questionIds: string[];
  currentIndex: number;
  selections: Record<string, string | null>;
  saveStatus: Record<string, SaveStatus>;
  /** Study Mode only: mark answered questions as correct (✓) or incorrect (✗). */
  feedback?: Record<string, StudyFeedback>;
  onJump: (index: number) => void;
}

/**
 * Direct navigation to any question. States are conveyed by text/shape as well as colour:
 * answered = filled with a check mark, unanswered = outlined, current = thick ring + aria-current,
 * not saved = "!" marker. In Study Mode, answered questions show ✓ (correct) or ✗ (incorrect).
 */
export default function QuestionPalette({
  questionIds,
  currentIndex,
  selections,
  saveStatus,
  feedback,
  onJump,
}: Props) {
  return (
    <nav aria-label="Question navigator">
      <ol className="palette">
        {questionIds.map((id, i) => {
          const answered = selections[id] != null;
          const failed = saveStatus[id] === "error";
          const current = i === currentIndex;
          const result = feedback?.[id];
          const wrong = result != null && !result.is_correct;
          const state =
            `${answered ? "answered" : "unanswered"}` +
            (result ? (result.is_correct ? ", correct" : ", incorrect") : "") +
            (failed ? ", not saved" : "");
          return (
            <li key={id}>
              <button
                type="button"
                className={[
                  "palette__btn",
                  answered ? "palette__btn--answered" : "",
                  current ? "palette__btn--current" : "",
                  failed ? "palette__btn--error" : "",
                  wrong ? "palette__btn--wrong" : "",
                ].join(" ")}
                aria-current={current ? "step" : undefined}
                aria-label={`Question ${i + 1}, ${state}`}
                onClick={() => onJump(i)}
              >
                <span aria-hidden="true">{i + 1}</span>
                {failed ? (
                  <span className="palette__mark" aria-hidden="true">
                    !
                  </span>
                ) : answered ? (
                  <span className="palette__mark" aria-hidden="true">
                    {wrong ? "✗" : "✓"}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
