/**
 * In-memory stand-in for the FastAPI backend, installed as global fetch in component tests.
 * It mirrors the real contract: per-attempt bearer tokens, option ownership checks,
 * immutable submitted attempts, and no correctness data before submission.
 */
import { vi } from "vitest";

interface Opt {
  id: string;
  text: string;
  correct: boolean;
}
interface Q {
  id: string;
  week: number;
  text: string;
  options: Opt[];
}
interface AttemptState {
  id: string;
  token: string;
  mode: "weekly" | "overall";
  week_no: number | null;
  study_mode: boolean;
  status: "in_progress" | "submitted";
  questions: { aqId: string; q: Q; order: Opt[]; selected: string | null }[];
  submitted_at: string | null;
}

export function makeBank(): Q[] {
  const bank: Q[] = [];
  for (let w = 1; w <= 12; w++) {
    for (let n = 1; n <= 10; n++) {
      const id = `q-${w}-${n}`;
      bank.push({
        id,
        week: w,
        text: `Week ${w} question ${n}?`,
        options: ["a", "b", "c", "d"].map((l, i) => ({
          id: `${id}-${l}`,
          text: `W${w}Q${n} option ${l}`,
          correct: i === n % 4,
        })),
      });
    }
  }
  return bank;
}

const LABELS = "ABCD";

export class FakeApi {
  bank = makeBank();
  attempts = new Map<string, AttemptState>();
  calls: { method: string; path: string; body?: unknown; auth?: string | null }[] = [];
  /** Answer saves fail while this is > 0 (decremented per failed call). */
  failSaves = 0;
  failCatalogue = 0;
  private counter = 0;

  install() {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => this.handle(input, init)));
    return this;
  }

  private json(status: number, body: unknown) {
    return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  }
  private err(status: number, code: string, message = code) {
    return this.json(status, { error: { code, message } });
  }

  private active(a: AttemptState) {
    return {
      id: a.id,
      mode: a.mode,
      week_no: a.week_no,
      title: a.mode === "weekly" ? `Week ${a.week_no}` : "Overall Quiz",
      study_mode: a.study_mode,
      status: a.status,
      started_at: "2026-10-22T10:00:00Z",
      submitted_at: a.submitted_at,
      total_questions: a.questions.length,
      answered_count: a.questions.filter((x) => x.selected).length,
      questions: a.questions.map((x, i) => ({
        attempt_question_id: x.aqId,
        position: i + 1,
        question_text: x.q.text,
        selected_option_id: x.selected,
        // Study Mode reveals correctness only for questions that have been answered.
        feedback:
          a.study_mode && x.selected
            ? { is_correct: x.order.find((o) => o.id === x.selected)!.correct, correct_option_id: x.order.find((o) => o.correct)!.id }
            : null,
        options: x.order.map((o, j) => ({ id: o.id, label: LABELS[j], text: o.text })),
      })),
    };
  }

  result(a: AttemptState) {
    const review = a.questions.map((x, i) => {
      const correct = x.order.find((o) => o.correct)!;
      const sel = x.order.find((o) => o.id === x.selected) ?? null;
      const status = !sel ? "unanswered" : sel.correct ? "correct" : "incorrect";
      return {
        attempt_question_id: x.aqId,
        position: i + 1,
        question_text: x.q.text,
        status,
        selected_option_id: sel?.id ?? null,
        selected_option_text: sel?.text ?? null,
        selected_label: sel ? LABELS[x.order.indexOf(sel)] : null,
        correct_option_id: correct.id,
        correct_option_text: correct.text,
        correct_label: LABELS[x.order.indexOf(correct)],
        options: x.order.map((o, j) => ({
          id: o.id,
          label: LABELS[j],
          text: o.text,
          is_correct: o.correct,
          is_selected: o.id === x.selected,
        })),
      };
    });
    const c = review.filter((r) => r.status === "correct").length;
    return {
      attempt_id: a.id,
      mode: a.mode,
      week_no: a.week_no,
      title: a.mode === "weekly" ? `Week ${a.week_no}` : "Overall Quiz",
      study_mode: a.study_mode,
      status: "submitted",
      started_at: "2026-10-22T10:00:00Z",
      submitted_at: a.submitted_at,
      total_questions: review.length,
      correct_count: c,
      incorrect_count: review.filter((r) => r.status === "incorrect").length,
      unanswered_count: review.filter((r) => r.status === "unanswered").length,
      score_correct: c,
      score_percent: Math.round((c * 10000) / review.length) / 100,
      review,
    };
  }

  /** Test helper: the correct option id for a displayed question. */
  correctOptionId(attemptId: string, aqId: string): string {
    const x = this.attempts.get(attemptId)!.questions.find((q) => q.aqId === aqId)!;
    return x.order.find((o) => o.correct)!.id;
  }

  private handle(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = new URL(String(input), "http://localhost");
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const method = (init?.method ?? "GET").toUpperCase();
    const headers = new Headers(init?.headers);
    const auth = headers.get("Authorization");
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    this.calls.push({ method, path, body, auth });

    if (method === "GET" && path === "/quizzes") {
      if (this.failCatalogue > 0) {
        this.failCatalogue--;
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      return this.json(200, {
        weeks: Array.from({ length: 12 }, (_, i) => ({
          week_no: i + 1,
          title: `Week ${i + 1}`,
          question_count: 10,
          available: true,
        })),
        overall: { title: "Overall Quiz", question_count: 120, available: true },
      });
    }
    if (method === "POST" && path === "/attempts") {
      const qs = body.mode === "weekly" ? this.bank.filter((q) => q.week === body.week_no) : [...this.bank];
      const id = `att-${++this.counter}`;
      // Deterministic "shuffle": rotate questions and options by the attempt counter.
      const rot = <T,>(arr: T[], k: number) => arr.map((_, i) => arr[(i + k) % arr.length]!);
      const a: AttemptState = {
        id,
        token: `tok-${this.counter}`,
        mode: body.mode,
        week_no: body.mode === "weekly" ? body.week_no : null,
        study_mode: body.study_mode === true,
        status: "in_progress",
        submitted_at: null,
        questions: rot(qs, this.counter).map((q, i) => ({
          aqId: `${id}-aq-${i}`,
          q,
          order: rot(q.options, i + this.counter),
          selected: null,
        })),
      };
      this.attempts.set(id, a);
      return this.json(201, { ...this.active(a), access_token: a.token });
    }

    const m = path.match(/^\/attempts\/([^/]+)(\/.*)?$/);
    if (!m) return this.err(404, "not_found");
    const a = this.attempts.get(m[1]!);
    if (!auth) return this.err(401, "missing_token");
    if (!a) return this.err(404, "attempt_not_found");
    if (auth !== `Bearer ${a.token}`) return this.err(403, "invalid_token");
    const rest = m[2] ?? "";

    if (method === "GET" && rest === "") return this.json(200, this.active(a));
    const ans = rest.match(/^\/questions\/([^/]+)\/answer$/);
    if (method === "PUT" && ans) {
      if (this.failSaves > 0) {
        this.failSaves--;
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      if (a.status !== "in_progress") return this.err(409, "attempt_not_in_progress");
      if (a.study_mode) return this.err(409, "study_mode_attempt");
      const x = a.questions.find((q) => q.aqId === ans[1]);
      if (!x) return this.err(404, "question_not_in_attempt");
      const opt = body.selected_option_id;
      if (opt !== null && !x.order.some((o) => o.id === opt)) return this.err(422, "option_not_in_question");
      x.selected = opt;
      return this.json(200, {
        attempt_question_id: x.aqId,
        selected_option_id: opt,
        answered_count: a.questions.filter((q) => q.selected).length,
        total_questions: a.questions.length,
        answered_at: opt ? "2026-10-22T10:01:00Z" : null,
      });
    }
    const study = rest.match(/^\/questions\/([^/]+)\/study-answer$/);
    if (method === "POST" && study) {
      if (this.failSaves > 0) {
        this.failSaves--;
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      if (!a.study_mode) return this.err(409, "not_study_mode");
      if (a.status !== "in_progress") return this.err(409, "attempt_not_in_progress");
      const x = a.questions.find((q) => q.aqId === study[1]);
      if (!x) return this.err(404, "question_not_in_attempt");
      const opt = body.selected_option_id;
      if (!x.order.some((o) => o.id === opt)) return this.err(422, "option_not_in_question");
      if (x.selected && x.selected !== opt) return this.err(409, "question_locked");
      x.selected = opt;
      const correct = x.order.find((o) => o.correct)!;
      const answeredQs = a.questions.filter((q) => q.selected);
      return this.json(200, {
        attempt_question_id: x.aqId,
        selected_option_id: opt,
        is_correct: opt === correct.id,
        correct_option_id: correct.id,
        answered_count: answeredQs.length,
        correct_count: answeredQs.filter((q) => q.order.find((o) => o.id === q.selected)!.correct).length,
        total_questions: a.questions.length,
      });
    }
    if (method === "POST" && rest === "/submit") {
      if (a.status === "in_progress") {
        a.status = "submitted";
        a.submitted_at = "2026-10-22T10:05:00Z";
      }
      return this.json(200, this.result(a));
    }
    if (method === "GET" && rest === "/result") {
      if (a.status !== "submitted") return this.err(409, "attempt_not_submitted");
      return this.json(200, this.result(a));
    }
    return this.err(404, "not_found");
  }
}
