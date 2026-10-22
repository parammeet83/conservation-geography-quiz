import type { SaveStatus } from "../pages/QuizPage";

interface Props {
  questionIds: string[];
  currentIndex: number;
  selections: Record<string, string | null>;
  saveStatus: Record<string, SaveStatus>;
  onJump: (index: number) => void;
}

/**
 * Direct navigation to any question. States are conveyed by text/shape as well as colour:
 * answered = filled with a check mark, unanswered = outlined, current = thick ring + aria-current,
 * not saved = "!" marker.
 */
export default function QuestionPalette({ questionIds, currentIndex, selections, saveStatus, onJump }: Props) {
  return (
    <nav aria-label="Question navigator">
      <ol className="palette">
        {questionIds.map((id, i) => {
          const answered = selections[id] != null;
          const failed = saveStatus[id] === "error";
          const current = i === currentIndex;
          const state = `${answered ? "answered" : "unanswered"}${failed ? ", not saved" : ""}`;
          return (
            <li key={id}>
              <button
                type="button"
                className={[
                  "palette__btn",
                  answered ? "palette__btn--answered" : "",
                  current ? "palette__btn--current" : "",
                  failed ? "palette__btn--error" : "",
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
                    ✓
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
