import { expect, test, type Page } from "@playwright/test";
import { choose, heading } from "./helpers";

async function noHorizontalOverflow(page: Page) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
}

test.use({ viewport: { width: 360, height: 740 } });

test("no horizontal overflow at 360px on home, quiz, dialog and results", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: /^Start Week 1,/ })).toBeVisible();
  await noHorizontalOverflow(page);

  await page.getByRole("button", { name: "Start Week 3, 10 questions" }).click();
  await expect(await heading(page)).toHaveText("Question 1 of 10");
  await noHorizontalOverflow(page);
  await choose(page, 0);

  // Longest option text in the bank (W3 Q6) must wrap, not overflow.
  for (let n = 1; n <= 10; n++) {
    await page.getByRole("button", { name: new RegExp(`^Question ${n},`) }).click();
    await noHorizontalOverflow(page);
  }

  await page.getByRole("button", { name: "Submit quiz" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await noHorizontalOverflow(page);
  await page.getByRole("dialog").getByRole("button", { name: "Submit quiz" }).click();
  await expect(page.getByRole("heading", { name: "Your results" })).toBeVisible();
  await noHorizontalOverflow(page);
});

test("keyboard: options are radio inputs reachable and selectable with the keyboard", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Start Week 2, 10 questions" }).click();
  await expect(await heading(page)).toHaveText("Question 1 of 10");
  const first = page.locator(".option input").first();
  await first.focus();
  await page.keyboard.press("Space");
  await expect(first).toBeChecked();
  await page.keyboard.press("ArrowDown");
  await expect(page.locator(".option input").nth(1)).toBeChecked();
  await expect(page.locator(".save--saved")).toBeVisible();

  await page.getByRole("button", { name: "Submit quiz" }).focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Submit quiz" })).toBeFocused();
});
