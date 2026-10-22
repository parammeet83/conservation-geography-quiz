import { expect, test } from "@playwright/test";
import { choose, guardAgainstAnswerLeaks, heading, identity, jumpTo, readCurrent, seedQuestions } from "./helpers";

test("overall journey: 120 unique questions, answers persist, submit and review", async ({ page }) => {
  const leaks: string[] = [];
  guardAgainstAnswerLeaks(page, leaks);

  await page.goto("/");
  await page.getByRole("button", { name: "Start Overall Quiz, 120 questions" }).click();
  await expect(await heading(page)).toHaveText("Question 1 of 120");
  await expect(page.getByRole("navigation", { name: "Question navigator" }).getByRole("button")).toHaveCount(120);

  // Walk all 120 questions with Next and compare against the full question bank.
  // The bank has identical stems in different weeks, so compare as a multiset.
  const shown = [];
  for (let n = 1; n <= 120; n++) {
    await expect(await heading(page)).toHaveText(`Question ${n} of 120`);
    shown.push(await readCurrent(page));
    if (n < 120) await page.getByRole("button", { name: "Next →" }).click();
  }
  await expect(page.getByRole("button", { name: "Next →" })).toBeDisabled();
  expect(shown.map(identity).sort()).toEqual(seedQuestions().map(identity).sort());
  expect(shown.every((q) => q.options.length === 4 && new Set(q.options).size === 4)).toBe(true);

  // Answer at the beginning, middle and end.
  await jumpTo(page, 1);
  await choose(page, 1);
  await jumpTo(page, 60);
  await choose(page, 2);
  await jumpTo(page, 120);
  await choose(page, 3);
  await expect(page.getByTestId("progress-text")).toHaveText("3 answered · 117 remaining");

  // Refresh and verify order and answers are restored.
  await page.reload();
  await expect(await heading(page)).toHaveText("Question 120 of 120");
  expect(await readCurrent(page)).toEqual(shown[119]);
  await expect(page.locator(".option input").nth(3)).toBeChecked();
  await jumpTo(page, 60);
  expect(await readCurrent(page)).toEqual(shown[59]);
  await expect(page.locator(".option input").nth(2)).toBeChecked();
  await jumpTo(page, 1);
  await expect(page.locator(".option input").nth(1)).toBeChecked();
  await expect(page.getByTestId("progress-text")).toHaveText("3 answered · 117 remaining");

  await page.getByRole("button", { name: "Submit quiz" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByTestId("dialog-unanswered")).toHaveText("117");
  await dialog.getByRole("button", { name: "Submit quiz" }).click();

  await expect(page.getByRole("heading", { name: "Your results" })).toBeVisible();
  await expect(page.getByTestId("count-unanswered")).toHaveText("117");
  const correct = Number(await page.getByTestId("count-correct").innerText());
  await expect(page.getByTestId("score")).toHaveText(`${correct} / 120`);
  await expect(page.getByTestId("percent")).toHaveText(`${((correct * 100) / 120).toFixed(2)}%`);
  await expect(page.getByTestId("review-item")).toHaveCount(120);
  await expect(page.getByText("Not answered")).toHaveCount(117);

  await page.getByRole("button", { name: /^Incorrect \(/ }).click();
  const incorrect = Number(await page.getByTestId("count-incorrect").innerText());
  await expect(page.getByTestId("review-item")).toHaveCount(incorrect);

  expect(leaks).toEqual([]);
});

test("a new overall attempt is shuffled independently of the previous one", async ({ page }) => {
  const orders: string[][] = [];
  for (let i = 0; i < 2; i++) {
    await page.goto("/");
    const created = page.waitForResponse((r) => r.url().endsWith("/api/v1/attempts") && r.status() === 201);
    await page.getByRole("button", { name: /Overall Quiz, 120 questions$/ }).click();
    const body = await (await created).json();
    orders.push(body.questions.map((q: { question_text: string }) => q.question_text));
    await expect(await heading(page)).toHaveText("Question 1 of 120");
  }
  // Same 120 questions in both attempts...
  expect([...orders[0]!].sort()).toEqual([...orders[1]!].sort());
  // ...in a different order (probability of identical 120-item orders is ~1/120!).
  expect(orders[0]).not.toEqual(orders[1]);
});
