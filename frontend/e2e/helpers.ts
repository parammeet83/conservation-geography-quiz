import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export interface Shown {
  text: string;
  options: string[];
}

/** Question-bank records from the committed, validated seed file. */
export function seedQuestions(): { week: number; text: string; options: string[] }[] {
  const path = fileURLToPath(new URL("../../data/seed/questions.json", import.meta.url));
  const doc = JSON.parse(readFileSync(path, "utf-8"));
  return doc.questions.map((q: { source_week: number; question_text: string; options: { option_text: string }[] }) => ({
    week: q.source_week,
    text: q.question_text,
    options: q.options.map((o) => o.option_text),
  }));
}

export const identity = (q: { text: string; options: string[] }) => `${q.text} || ${[...q.options].sort().join(" | ")}`;

export async function readCurrent(page: Page): Promise<Shown> {
  const text = (await page.locator("legend.question__text").innerText()).trim();
  const options = await page.locator(".option .option__text").evaluateAll((els) =>
    els.map((e) => (e.textContent ?? "").replace(/^Option [A-D]: /, "").trim()),
  );
  return { text, options };
}

export async function heading(page: Page) {
  return page.getByRole("heading", { level: 1 });
}

export async function choose(page: Page, index: number) {
  await page.locator(".option").nth(index).click();
  await expect(page.locator(".save--saved")).toBeVisible();
}

export async function jumpTo(page: Page, n: number) {
  await page.getByRole("button", { name: new RegExp(`^Question ${n},`) }).click();
  await expect(await heading(page)).toHaveText(new RegExp(`^Question ${n} of`));
}

/** Fails the test if any active-attempt API response carries correctness data. */
export function guardAgainstAnswerLeaks(page: Page, leaks: string[]) {
  page.on("response", async (res) => {
    const url = res.url();
    if (!url.includes("/api/v1/attempts") || url.endsWith("/submit") || url.endsWith("/result")) return;
    try {
      const body = await res.text();
      if (/is_correct|correct_option|correct_label|score_percent/.test(body)) leaks.push(url);
    } catch {
      // Response bodies of navigations can be unavailable; ignore.
    }
  });
}
