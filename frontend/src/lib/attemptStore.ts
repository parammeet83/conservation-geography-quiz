import type { QuizMode } from "../api/types";

/**
 * Per-browser record of attempts started here, so a refresh or a later visit can resume.
 *
 * The attempt access token is kept in localStorage, scoped to one attempt. It is never
 * placed in a URL or logged. Anyone with access to this browser profile could read it,
 * which is acceptable for an anonymous practice quiz (see docs/RUN_AND_VERIFY.md).
 */
export interface StoredAttempt {
  attemptId: string;
  token: string;
  mode: QuizMode;
  weekNo: number | null;
  title: string;
  submitted: boolean;
  createdAt: string;
}

const KEY = "cgq.attempts.v1";
const MAX_RECORDS = 50;

function readAll(): StoredAttempt[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeAll(records: StoredAttempt[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(records.slice(0, MAX_RECORDS)));
  } catch {
    // Storage may be unavailable (private mode, quota); the current page still works.
  }
}

export const attemptStore = {
  save(record: StoredAttempt): void {
    writeAll([record, ...readAll().filter((r) => r.attemptId !== record.attemptId)]);
  },

  get(attemptId: string): StoredAttempt | undefined {
    return readAll().find((r) => r.attemptId === attemptId);
  },

  markSubmitted(attemptId: string): void {
    writeAll(readAll().map((r) => (r.attemptId === attemptId ? { ...r, submitted: true } : r)));
  },

  remove(attemptId: string): void {
    writeAll(readAll().filter((r) => r.attemptId !== attemptId));
  },

  /** Most recent unsubmitted attempt for a quiz scope, if any. */
  inProgressFor(mode: QuizMode, weekNo: number | null): StoredAttempt | undefined {
    return readAll().find((r) => !r.submitted && r.mode === mode && r.weekNo === weekNo);
  },
};
