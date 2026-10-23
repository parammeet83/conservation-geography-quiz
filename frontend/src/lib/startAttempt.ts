import { api } from "../api/client";
import type { QuizMode } from "../api/types";
import { attemptStore } from "./attemptStore";

/** Create a fresh, server-shuffled attempt and remember its access token in this browser. */
export async function startAttempt(mode: QuizMode, weekNo: number | null, studyMode = false): Promise<string> {
  const created = await api.createAttempt(mode, weekNo, studyMode);
  attemptStore.save({
    attemptId: created.id,
    token: created.access_token,
    mode: created.mode,
    weekNo: created.week_no,
    title: created.title,
    studyMode: created.study_mode,
    submitted: false,
    createdAt: created.started_at,
  });
  return created.id;
}
