import { expect, test } from "@playwright/test";
import { heading, identity, jumpTo, readCurrent, seedQuestions } from "./helpers";

test("study mode journey: Week 1 immediate feedback, locking, summary and results", async ({ page }) => {
  const created = page.waitForResponse((r) => r.url().endsWith("/api/v1/attempts") && r.status() === 201);
  await page.goto("/");
  await expect(page.getByRole("radio", { name: /Quiz Mode/ })).toBeChecked();
  await page.getByRole("radio", { name: /Study Mode/ }).check();
  await page.getByRole("button", { name: "Start Week 1 in Study Mode, 10 questions" }).click();
  await expect(await heading(page)).toHaveText("Question 1 of 10");

  // The initial payload carries no answer information.
  const body = await (await created).json();
  expect(body.study_mode).toBe(true);
  expect(JSON.stringify(body)).not.toMatch(/is_correct|correct_option/);
  expect(body.questions.every((q: { feedback: unknown }) => q.feedback === null)).toBe(true);

  // Only Week 1 questions.
  const week1 = new Set(seedQuestions().filter((q) => q.week === 1).map(identity));
  let correct = 0;
  for (let n = 1; n <= 10; n++) {
    if (n > 1) await page.getByRole("button", { name: "Next →" }).click();
    await expect(await heading(page)).toHaveText(`Question ${n} of 10`);
    expect(week1.has(identity(await readCurrent(page)))).toBe(true);
    await expect(page.getByTestId("study-feedback")).toHaveCount(0);

    const checked = page.waitForResponse((r) => r.url().endsWith("/study-answer"));
    await page.locator(".option").nth(n % 4).click();
    const res = await (await checked).json();
    const feedback = page.getByTestId("study-feedback");
    await expect(feedback).toHaveText(res.is_correct ? /Correct!/ : /Incorrect\. The correct answer is/);
    if (res.is_correct) correct++;

    // Exactly one option is marked correct, and it is the one the server named.
    await expect(page.locator(".option--correct")).toHaveCount(1);
    const correctIndex = await page
      .locator(".option input")
      .evaluateAll((els, id) => els.findIndex((e) => (e as HTMLInputElement).value === id), res.correct_option_id);
    await expect(page.locator(".option").nth(correctIndex)).toHaveClass(/option--correct/);
    await expect(page.locator(".option--incorrect")).toHaveCount(res.is_correct ? 0 : 1);

    // Locked: every radio is disabled after the first pick.
    for (let i = 0; i < 4; i++) await expect(page.locator(".option input").nth(i)).toBeDisabled();
  }
  await expect(page.getByTestId("study-tally")).toContainText(`${correct} correct`);
  await expect(page.getByTestId("study-tally")).toContainText(`${10 - correct} incorrect`);

  // Refresh: feedback and locks persist.
  await page.reload();
  await expect(await heading(page)).toHaveText("Question 10 of 10");
  await expect(page.getByTestId("study-feedback")).toBeVisible();
  await expect(page.locator(".option input").first()).toBeDisabled();

  const summary = page.getByTestId("study-summary");
  await expect(summary).toContainText(`${correct} correct and ${10 - correct} incorrect`);
  await summary.getByRole("button", { name: "See full summary" }).click();
  await expect(page.getByRole("heading", { name: "Study session summary" })).toBeVisible();
  await expect(page.getByTestId("score")).toHaveText(`${correct} / 10`);
  await expect(page.getByTestId("review-item")).toHaveCount(10);
});

test("study mode overall quiz: 120 questions, feedback per answer, quiz mode unaffected", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("radio", { name: /Study Mode/ }).check();
  await page.getByRole("button", { name: "Start Overall Quiz in Study Mode, 120 questions" }).click();
  await expect(await heading(page)).toHaveText("Question 1 of 120");
  await expect(page.getByRole("navigation", { name: "Question navigator" }).getByRole("button")).toHaveCount(120);
  for (const n of [1, 60, 120]) {
    await jumpTo(page, n);
    await page.locator(".option").first().click();
    await expect(page.getByTestId("study-feedback")).toBeVisible();
  }
  await expect(page.getByTestId("progress-text")).toHaveText("3 answered · 117 remaining");

  // Quiz Mode in the same browser still behaves as before: no feedback, answers editable.
  await page.goto("/");
  await expect(page.getByRole("radio", { name: /Quiz Mode/ })).toBeChecked();
  await page.getByRole("button", { name: "Start Week 2, 10 questions" }).click();
  await expect(await heading(page)).toHaveText("Question 1 of 10");
  await page.locator(".option").first().click();
  await expect(page.locator(".save--saved")).toBeVisible();
  await page.locator(".option").nth(1).click();
  await expect(page.locator(".option input").nth(1)).toBeChecked();
  await expect(page.getByTestId("study-feedback")).toHaveCount(0);
  await expect(page.locator(".option--correct, .option--incorrect")).toHaveCount(0);
});

test("study mode at 360px has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/");
  await page.getByRole("radio", { name: /Study Mode/ }).check();
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(await overflow()).toBe(false);
  await page.getByRole("button", { name: "Start Week 3 in Study Mode, 10 questions" }).click();
  await page.locator(".option").nth(2).click();
  await expect(page.getByTestId("study-feedback")).toBeVisible();
  expect(await overflow()).toBe(false);
});
