import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import App from "../src/App";
import { FakeApi } from "./fakeApi";

let fake: FakeApi;

beforeEach(() => {
  window.localStorage.clear();
  fake = new FakeApi().install();
});

afterEach(() => {
  window.localStorage.clear();
});

function renderAt(path = "/") {
  const user = userEvent.setup();
  const utils = render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
  return { user, ...utils };
}

type User = ReturnType<typeof userEvent.setup>;

async function startStudy(user: User, name: RegExp) {
  await user.click(await screen.findByRole("radio", { name: /Study Mode/ }));
  await user.click(await screen.findByRole("button", { name }));
  await screen.findByRole("heading", { level: 1, name: /Question 1 of/ });
}

function radios() {
  return screen.getAllByRole("radio") as HTMLInputElement[];
}

/** The displayed question state held by the fake server for the current attempt. */
function shown(index: number) {
  const attempt = [...fake.attempts.values()].at(-1)!;
  return attempt.questions[index]!;
}

function optionLabel(text: string) {
  return screen.getByText(text).closest("label")!;
}

describe("mode selection", () => {
  it("defaults to Quiz Mode and keeps the existing quiz behaviour", async () => {
    const { user } = renderAt("/");
    const quizRadio = await screen.findByRole("radio", { name: /Quiz Mode/ });
    expect(quizRadio).toBeChecked();
    expect(screen.getByRole("radio", { name: /Study Mode/ })).not.toBeChecked();

    await user.click(screen.getByRole("button", { name: "Start Week 2, 10 questions" }));
    await screen.findByRole("heading", { level: 1, name: "Question 1 of 10" });
    expect(fake.calls.find((c) => c.method === "POST")?.body).toEqual({ mode: "weekly", week_no: 2 });
    expect(screen.queryByTestId("study-tally")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit quiz" })).toBeInTheDocument();

    // Quiz Mode: selecting reveals nothing and the answer can still be changed.
    await user.click(radios()[0]!);
    await screen.findByText(/Answer saved/);
    expect(screen.queryByTestId("study-feedback")).not.toBeInTheDocument();
    expect(radios().every((r) => !r.disabled)).toBe(true);
    expect(fake.calls.some((c) => c.path.endsWith("/study-answer"))).toBe(false);
  });

  it("starts a weekly quiz in Study Mode when selected", async () => {
    const { user } = renderAt("/");
    await startStudy(user, /^Start Week 4 in Study Mode, 10 questions/);
    expect(fake.calls.find((c) => c.method === "POST")?.body).toEqual({ mode: "weekly", week_no: 4, study_mode: true });
    expect(screen.getByText(/Study Mode/, { selector: ".quiz-header__scope *" })).toBeInTheDocument();
    expect(screen.getByText(/Week 4 question \d+\?/)).toBeInTheDocument();
    expect(screen.getByTestId("study-tally")).toHaveTextContent("0 correct · ✗ 0 incorrect");
    expect(screen.getByRole("button", { name: "Finish session" })).toBeInTheDocument();
  });
});

describe("study mode feedback", () => {
  it("does not reveal any answer before a selection", async () => {
    const { user } = renderAt("/");
    await startStudy(user, /^Start Week 1 in Study Mode/);
    expect(screen.queryByTestId("study-feedback")).not.toBeInTheDocument();
    expect(screen.queryByText(/Correct answer/)).not.toBeInTheDocument();
    expect(document.querySelector(".option--correct, .option--incorrect")).toBeNull();
    expect(screen.getByText(/Choose an answer to check it/)).toBeInTheDocument();
  });

  it("shows immediate positive feedback and locks the question after a correct pick", async () => {
    const { user } = renderAt("/");
    await startStudy(user, /^Start Week 3 in Study Mode/);
    const q = shown(0);
    const correct = q.order.find((o) => o.correct)!;
    await user.click(screen.getByRole("radio", { name: new RegExp(correct.text) }));

    expect(await screen.findByTestId("study-feedback")).toHaveTextContent("Correct!");
    const row = optionLabel(correct.text);
    expect(row).toHaveClass("option--correct");
    expect(within(row).getByText("✓ Correct answer")).toBeInTheDocument();
    expect(radios().every((r) => r.disabled)).toBe(true);
    expect(screen.getByTestId("study-tally")).toHaveTextContent("1 correct · ✗ 0 incorrect");
    expect(fake.calls.filter((c) => c.path.endsWith("/study-answer"))).toHaveLength(1);
    expect(fake.calls.find((c) => c.path.endsWith("/study-answer"))?.body).toEqual({
      selected_option_id: correct.id,
    });
  });

  it("marks a wrong pick red and the correct option green", async () => {
    const { user } = renderAt("/");
    await startStudy(user, /^Start Week 5 in Study Mode/);
    const q = shown(0);
    const correct = q.order.find((o) => o.correct)!;
    const wrong = q.order.find((o) => !o.correct)!;
    const correctLabel = "ABCD"[q.order.indexOf(correct)];
    await user.click(screen.getByRole("radio", { name: new RegExp(wrong.text) }));

    const fb = await screen.findByTestId("study-feedback");
    expect(fb).toHaveTextContent(`Incorrect. The correct answer is ${correctLabel}. ${correct.text}.`);
    expect(optionLabel(wrong.text)).toHaveClass("option--incorrect");
    expect(within(optionLabel(wrong.text)).getByText("✗ Your answer")).toBeInTheDocument();
    expect(optionLabel(correct.text)).toHaveClass("option--correct");
    expect(screen.getByTestId("study-tally")).toHaveTextContent("0 correct · ✗ 1 incorrect");
    expect(screen.getByRole("button", { name: "Question 1, answered, incorrect" })).toBeInTheDocument();
  });

  it("ignores further clicks on a locked question", async () => {
    const { user } = renderAt("/");
    await startStudy(user, /^Start Week 6 in Study Mode/);
    const q = shown(0);
    const [first, second] = q.order;
    await user.click(screen.getByRole("radio", { name: new RegExp(first!.text) }));
    await screen.findByTestId("study-feedback");
    await user.click(screen.getByRole("radio", { name: new RegExp(second!.text) }));
    expect(screen.getByRole("radio", { name: new RegExp(first!.text) })).toBeChecked();
    expect(screen.getByRole("radio", { name: new RegExp(second!.text) })).not.toBeChecked();
    expect(fake.calls.filter((c) => c.path.endsWith("/study-answer"))).toHaveLength(1);
    expect(q.selected).toBe(first!.id);
    expect(screen.queryByRole("button", { name: "Clear selection" })).not.toBeInTheDocument();
  });

  it("keeps the choice and retries when checking fails", async () => {
    const { user } = renderAt("/");
    await startStudy(user, /^Start Week 7 in Study Mode/);
    const correct = shown(0).order.find((o) => o.correct)!;
    fake.failSaves = 1;
    await user.click(screen.getByRole("radio", { name: new RegExp(correct.text) }));
    expect(await screen.findByText(/Could not check your answer/)).toBeInTheDocument();
    expect(screen.queryByTestId("study-feedback")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: new RegExp(correct.text) })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("study-feedback")).toHaveTextContent("Correct!");
  });
});

describe("study session scoring and completion", () => {
  it("tracks the score, shows a completion summary, then the full results", async () => {
    const { user } = renderAt("/");
    await startStudy(user, /^Start Week 8 in Study Mode/);
    for (let i = 0; i < 10; i++) {
      const q = shown(i);
      const pick = i < 7 ? q.order.find((o) => o.correct)! : q.order.find((o) => !o.correct)!;
      await user.click(screen.getByRole("radio", { name: new RegExp(pick.text) }));
      await screen.findByTestId("study-feedback");
      if (i < 9) await user.click(screen.getByRole("button", { name: "Next →" }));
    }
    expect(screen.getByTestId("study-tally")).toHaveTextContent("7 correct · ✗ 3 incorrect");
    const summary = screen.getByTestId("study-summary");
    expect(within(summary).getByRole("heading", { name: "Study session complete" })).toBeInTheDocument();
    expect(summary).toHaveTextContent("7 correct and 3 incorrect (70.00%)");

    await user.click(within(summary).getByRole("button", { name: "See full summary" }));
    expect(await screen.findByRole("heading", { name: "Study session summary" })).toBeInTheDocument();
    expect(screen.getByTestId("score")).toHaveTextContent("7 / 10");
    expect(screen.getByTestId("count-incorrect")).toHaveTextContent("3");
    expect(screen.getAllByTestId("review-item")).toHaveLength(10);

    // Try again keeps Study Mode.
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("heading", { level: 1, name: "Question 1 of 10" });
    expect(fake.calls.filter((c) => c.method === "POST" && c.path === "/attempts").at(-1)?.body).toEqual({
      mode: "weekly",
      week_no: 8,
      study_mode: true,
    });
  });

  it("can finish early through the confirmation dialog", async () => {
    const { user } = renderAt("/");
    await startStudy(user, /^Start Week 9 in Study Mode/);
    await user.click(radios()[0]!);
    await screen.findByTestId("study-feedback");
    await user.click(screen.getByRole("button", { name: "Finish session" }));
    const dialog = await screen.findByRole("dialog", { name: "Finish this study session?" });
    expect(within(dialog).getByTestId("dialog-unanswered")).toHaveTextContent("9");
    expect(dialog).toHaveTextContent("Finish anyway?");
    await user.click(within(dialog).getByRole("button", { name: "Finish session" }));
    expect(await screen.findByTestId("count-unanswered")).toHaveTextContent("9");
  });
});

describe("overall quiz and resume in study mode", () => {
  it("runs the 120-question overall quiz in Study Mode with per-question feedback", async () => {
    const { user } = renderAt("/");
    await startStudy(user, /^Start Overall Quiz in Study Mode, 120 questions/);
    expect(fake.calls.find((c) => c.method === "POST")?.body).toEqual({ mode: "overall", study_mode: true });
    const palette = screen.getByRole("navigation", { name: "Question navigator" });
    expect(within(palette).getAllByRole("button")).toHaveLength(120);

    const last = shown(119);
    await user.click(within(palette).getByRole("button", { name: "Question 120, unanswered" }));
    await user.click(screen.getByRole("radio", { name: new RegExp(last.order.find((o) => o.correct)!.text) }));
    expect(await screen.findByTestId("study-feedback")).toHaveTextContent("Correct!");
    expect(within(palette).getByRole("button", { name: "Question 120, answered, correct" })).toBeInTheDocument();
    expect(screen.queryByTestId("study-summary")).not.toBeInTheDocument();
  });

  it("restores feedback and locks answered questions after a reload", async () => {
    const first = renderAt("/");
    await startStudy(first.user, /^Start Week 10 in Study Mode/);
    const q = shown(0);
    const wrong = q.order.find((o) => !o.correct)!;
    await first.user.click(screen.getByRole("radio", { name: new RegExp(wrong.text) }));
    await screen.findByTestId("study-feedback");
    const attemptId = [...fake.attempts.keys()].at(-1)!;
    first.unmount();

    renderAt(`/attempts/${attemptId}`);
    expect(await screen.findByTestId("study-feedback")).toHaveTextContent("Incorrect.");
    expect(screen.getByRole("radio", { name: new RegExp(wrong.text) })).toBeChecked();
    expect(radios().every((r) => r.disabled)).toBe(true);
    expect(optionLabel(q.order.find((o) => o.correct)!.text)).toHaveClass("option--correct");
    expect(fake.calls.filter((c) => c.method === "POST" && c.path === "/attempts")).toHaveLength(1);
  });

  it("offers Resume only for the matching mode", async () => {
    const first = renderAt("/");
    await startStudy(first.user, /^Start Week 11 in Study Mode/);
    first.unmount();
    const { user } = renderAt("/");
    await screen.findByRole("button", { name: /^Start Week 11, 10 questions/ });
    expect(screen.queryByRole("link", { name: /Resume Week 11/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Study Mode/ }));
    await waitFor(() => expect(screen.getByRole("link", { name: /Resume Week 11 in Study Mode/ })).toBeInTheDocument());
  });
});
