import { expect, test } from "@playwright/test";
import { choose, guardAgainstAnswerLeaks, heading, identity, jumpTo, readCurrent, seedQuestions } from "./helpers";

test("weekly journey: Week 1 start, answer, navigate, refresh, submit, review, try again", async ({ page }) => {
  const leaks: string[] = [];
  guardAgainstAnswerLeaks(page, leaks);

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Conservation Geography Quiz" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Start Week \d+, 10 questions$/ })).toHaveCount(12);
  await expect(page.getByRole("button", { name: /^Start Overall Quiz, 120 questions$/ })).toBeVisible();

  await page.getByRole("button", { name: "Start Week 1, 10 questions" }).click();
  await expect(await heading(page)).toHaveText("Question 1 of 10");
  await expect(page).toHaveURL(/\/attempts\/[0-9a-f-]{36}/);
  const attemptUrl = page.url().split("?")[0]!;
  expect(attemptUrl).not.toContain("token");

  // Exactly the ten Week 1 questions, each with its own four options.
  const week1 = seedQuestions().filter((q) => q.week === 1).map(identity).sort();
  const shown = [];
  for (let n = 1; n <= 10; n++) {
    await jumpTo(page, n);
    shown.push(await readCurrent(page));
  }
  expect(shown.map(identity).sort()).toEqual(week1);
  expect(shown.every((q) => q.options.length === 4)).toBe(true);

  // Answer three questions, including changing one answer.
  await jumpTo(page, 1);
  await choose(page, 0);
  await page.getByRole("button", { name: "Next →" }).click();
  await expect(await heading(page)).toHaveText("Question 2 of 10");
  await choose(page, 2);
  await choose(page, 3); // changed answer
  await jumpTo(page, 7);
  await choose(page, 1);
  await expect(page.getByTestId("progress-text")).toHaveText("3 answered · 7 remaining");
  await page.getByRole("button", { name: "← Previous" }).click();
  await expect(await heading(page)).toHaveText("Question 6 of 10");

  // Refresh: same attempt, same order, answers restored.
  const q2Before = shown[1]!;
  await page.reload();
  await expect(await heading(page)).toHaveText("Question 6 of 10");
  await expect(page.getByTestId("progress-text")).toHaveText("3 answered · 7 remaining");
  await jumpTo(page, 2);
  expect(await readCurrent(page)).toEqual(q2Before);
  await expect(page.locator(".option input").nth(3)).toBeChecked();
  await jumpTo(page, 7);
  await expect(page.locator(".option input").nth(1)).toBeChecked();
  expect(page.url().split("?")[0]).toBe(attemptUrl);

  // Submit with confirmation.
  await page.getByRole("button", { name: "Submit quiz" }).click();
  const dialog = page.getByRole("dialog", { name: "Submit this quiz?" });
  await expect(dialog.getByTestId("dialog-answered")).toHaveText("3");
  await expect(dialog.getByTestId("dialog-unanswered")).toHaveText("7");
  await expect(dialog).toContainText("You have 7 unanswered questions. Submit anyway?");
  await dialog.getByRole("button", { name: "Submit quiz" }).click();

  await expect(page.getByRole("heading", { name: "Your results" })).toBeVisible();
  await expect(page).toHaveURL(/\/result$/);
  const correct = Number(await page.getByTestId("count-correct").innerText());
  const incorrect = Number(await page.getByTestId("count-incorrect").innerText());
  await expect(page.getByTestId("count-unanswered")).toHaveText("7");
  expect(correct + incorrect).toBe(3);
  await expect(page.getByTestId("score")).toHaveText(`${correct} / 10`);
  await expect(page.getByTestId("percent")).toHaveText(`${(correct * 10).toFixed(2)}%`);
  const items = page.getByTestId("review-item");
  await expect(items).toHaveCount(10);
  for (let i = 0; i < 10; i++) {
    await expect(items.nth(i)).toContainText("Correct answer");
    await expect(items.nth(i).locator(".badge")).toHaveText(/Correct|Incorrect|Unanswered/);
  }
  await expect(page.getByText("Not answered")).toHaveCount(7);

  // Refreshing the results keeps them; the attempt cannot be resumed for editing.
  await page.reload();
  await expect(page.getByTestId("score")).toHaveText(`${correct} / 10`);

  // Try again creates a new attempt.
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(await heading(page)).toHaveText("Question 1 of 10");
  expect(page.url().split("?")[0]).not.toBe(attemptUrl);
  await expect(page.getByTestId("progress-text")).toHaveText("0 answered · 10 remaining");
  await expect(page.locator(".option input:checked")).toHaveCount(0);

  expect(leaks).toEqual([]);
});

test("another weekly quiz (Week 12) contains only its own questions", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Start Week 12, 10 questions" }).click();
  await expect(await heading(page)).toHaveText("Question 1 of 10");
  const expected = seedQuestions().filter((q) => q.week === 12).map(identity).sort();
  const shown = [];
  for (let n = 1; n <= 10; n++) {
    await jumpTo(page, n);
    shown.push(identity(await readCurrent(page)));
  }
  expect(shown.sort()).toEqual(expected);
});
