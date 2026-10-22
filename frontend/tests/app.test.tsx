import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import App from "../src/App";
import { attemptStore } from "../src/lib/attemptStore";
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

async function startQuiz(user: ReturnType<typeof userEvent.setup>, name: RegExp) {
  await user.click(await screen.findByRole("button", { name }));
  await screen.findByRole("heading", { level: 1, name: /Question 1 of/ });
}

function currentRadios() {
  return screen.getAllByRole("radio") as HTMLInputElement[];
}

describe("home page", () => {
  it("shows twelve weekly quizzes and the overall quiz with counts from the API", async () => {
    renderAt("/");
    expect(screen.getByRole("heading", { level: 1, name: "Conservation Geography Quiz" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /^Start Overall Quiz, 120 questions/ })).toBeInTheDocument();
    for (let w = 1; w <= 12; w++) {
      expect(screen.getByRole("button", { name: `Start Week ${w}, 10 questions` })).toBeInTheDocument();
    }
    expect(fake.calls.filter((c) => c.path === "/quizzes")).toHaveLength(1);
  });

  it("shows an error with a working retry when the catalogue fails to load", async () => {
    fake.failCatalogue = 1;
    const { user } = renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not reach the server/);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("button", { name: /Start Week 3,/ })).toBeInTheDocument();
  });
});

describe("weekly quiz", () => {
  it("starts Week 3 with its ten questions and four labelled options", async () => {
    const { user } = renderAt("/");
    await startQuiz(user, /^Start Week 3,/);
    expect(fake.calls.find((c) => c.method === "POST")?.body).toEqual({ mode: "weekly", week_no: 3 });
    expect(screen.getByText("Week 3", { selector: ".quiz-header__scope" })).toBeInTheDocument();
    expect(currentRadios()).toHaveLength(4);
    expect(screen.getByText(/Week 3 question \d+\?/)).toBeInTheDocument();
    const palette = screen.getByRole("navigation", { name: "Question navigator" });
    expect(within(palette).getAllByRole("button")).toHaveLength(10);
    expect(screen.getByTestId("progress-text")).toHaveTextContent("0 answered · 10 remaining");
    // Option labels A-D are generated for display.
    expect(screen.getByText("Option A:", { exact: false })).toBeInTheDocument();
  });

  it("saves the selected option id, preserves answers across navigation, and updates progress", async () => {
    const { user } = renderAt("/");
    await startQuiz(user, /^Start Week 1,/);
    const firstOption = currentRadios()[2]!;
    await user.click(firstOption);
    await screen.findByText(/Answer saved/);
    const put = fake.calls.find((c) => c.method === "PUT")!;
    expect(put.body).toEqual({ selected_option_id: firstOption.value });
    expect(put.auth).toMatch(/^Bearer tok-/);
    expect(screen.getByTestId("progress-text")).toHaveTextContent("1 answered · 9 remaining");

    await user.click(screen.getByRole("button", { name: "Next →" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Question 2 of 10");
    expect(currentRadios().every((r) => !r.checked)).toBe(true);

    await user.click(screen.getByRole("button", { name: "← Previous" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Question 1 of 10");
    expect(currentRadios()[2]!.checked).toBe(true);

    // Direct navigation through the palette
    await user.click(screen.getByRole("button", { name: "Question 10, unanswered" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Question 10 of 10");
    expect(screen.getByRole("button", { name: "Next →" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Question 1, answered" })).toBeInTheDocument();
  });

  it("allows changing and clearing an answer", async () => {
    const { user } = renderAt("/");
    await startQuiz(user, /^Start Week 2,/);
    await user.click(currentRadios()[0]!);
    await user.click(currentRadios()[1]!);
    await waitFor(() => expect(currentRadios()[1]!.checked).toBe(true));
    await user.click(screen.getByRole("button", { name: "Clear selection" }));
    await screen.findByText(/Cleared/);
    expect(currentRadios().every((r) => !r.checked)).toBe(true);
    const puts = fake.calls.filter((c) => c.method === "PUT").map((c) => (c.body as { selected_option_id: unknown }).selected_option_id);
    expect(puts.at(-1)).toBeNull();
    expect(screen.getByTestId("progress-text")).toHaveTextContent("0 answered · 10 remaining");
  });

  it("shows a save failure, keeps the selection, and recovers on retry", async () => {
    const { user } = renderAt("/");
    await startQuiz(user, /^Start Week 4,/);
    fake.failSaves = 1;
    await user.click(currentRadios()[1]!);
    expect(await screen.findByText(/Not saved/)).toBeInTheDocument();
    expect(screen.queryByText(/Answer saved/)).not.toBeInTheDocument();
    expect(currentRadios()[1]!.checked).toBe(true);
    expect(screen.getByRole("button", { name: /Question 1, answered, not saved/ })).toBeInTheDocument();

    // Submission is blocked while an answer is unsaved.
    await user.click(screen.getByRole("button", { name: "Submit quiz" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/1 answer is not saved yet/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Submit quiz" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "Retry saving" }));
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Submit quiz" })).toBeEnabled());
    await user.click(within(dialog).getByRole("button", { name: "Review answers" }));
    expect(await screen.findByText(/Answer saved/)).toBeInTheDocument();
  });

  it("confirms before submitting, warns about unanswered questions, and shows results with review", async () => {
    const { user } = renderAt("/");
    await startQuiz(user, /^Start Week 5,/);
    const attemptId = [...fake.attempts.keys()][0]!;
    const attempt = fake.attempts.get(attemptId)!;

    // Answer Q1 correctly and Q2 incorrectly; leave the rest unanswered.
    const q1 = attempt.questions[0]!;
    await user.click(screen.getByRole("radio", { name: new RegExp(q1.order.find((o) => o.correct)!.text) }));
    await screen.findByText(/Answer saved/);
    await user.click(screen.getByRole("button", { name: "Next →" }));
    const q2 = attempt.questions[1]!;
    await user.click(screen.getByRole("radio", { name: new RegExp(q2.order.find((o) => !o.correct)!.text) }));
    await screen.findByText(/Answer saved/);

    await user.click(screen.getByRole("button", { name: "Submit quiz" }));
    let dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("dialog-answered")).toHaveTextContent("2");
    expect(within(dialog).getByTestId("dialog-unanswered")).toHaveTextContent("8");
    expect(within(dialog).getByText(/You have 8 unanswered questions\. Submit anyway\?/)).toBeInTheDocument();

    // Going back does not submit.
    await user.click(within(dialog).getByRole("button", { name: "Review answers" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fake.calls.some((c) => c.path.endsWith("/submit"))).toBe(false);

    await user.click(screen.getByRole("button", { name: "Submit quiz" }));
    dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Submit quiz" }));

    expect(await screen.findByRole("heading", { name: "Your results" })).toBeInTheDocument();
    expect(fake.calls.filter((c) => c.path.endsWith("/submit"))).toHaveLength(1);
    expect(screen.getByTestId("score")).toHaveTextContent("1 / 10");
    expect(screen.getByTestId("percent")).toHaveTextContent("10.00%");
    expect(screen.getByTestId("count-correct")).toHaveTextContent("1");
    expect(screen.getByTestId("count-incorrect")).toHaveTextContent("1");
    expect(screen.getByTestId("count-unanswered")).toHaveTextContent("8");

    const items = screen.getAllByTestId("review-item");
    expect(items).toHaveLength(10);
    expect(within(items[0]!).getByText("Correct", { selector: ".badge" })).toBeInTheDocument();
    expect(within(items[1]!).getByText("Incorrect", { selector: ".badge" })).toBeInTheDocument();
    expect(within(items[2]!).getByText("Not answered")).toBeInTheDocument();
    expect(within(items[2]!).getByText("Unanswered", { selector: ".badge" })).toBeInTheDocument();
    const correctRow = within(items[2]!).getByText("Correct answer", { selector: "dt" }).parentElement!;
    expect(correctRow).toHaveTextContent(attempt.questions[2]!.order.find((o) => o.correct)!.text);

    await user.click(screen.getByRole("button", { name: /Unanswered \(8\)/ }));
    expect(screen.getAllByTestId("review-item")).toHaveLength(8);
    expect(attemptStore.get(attemptId)?.submitted).toBe(true);
  });

  it("Try again creates a fresh attempt for the same week", async () => {
    const { user } = renderAt("/");
    await startQuiz(user, /^Start Week 6,/);
    await user.click(screen.getByRole("button", { name: "Submit quiz" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Submit quiz" }));
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    await screen.findByRole("heading", { level: 1, name: "Question 1 of 10" });
    const posts = fake.calls.filter((c) => c.method === "POST" && c.path === "/attempts");
    expect(posts.map((p) => p.body)).toEqual([
      { mode: "weekly", week_no: 6 },
      { mode: "weekly", week_no: 6 },
    ]);
    expect(fake.attempts.size).toBe(2);
  });
});

describe("resume and access", () => {
  it("restores a saved attempt (order and answers) after a reload without creating a new one", async () => {
    const first = renderAt("/");
    await startQuiz(first.user, /^Start Week 8,/);
    const order = screen.getAllByRole("radio").map((r) => (r as HTMLInputElement).value);
    await first.user.click(currentRadios()[3]!);
    await screen.findByText(/Answer saved/);
    const attemptId = [...fake.attempts.keys()][0]!;
    first.unmount();

    renderAt(`/attempts/${attemptId}`);
    await screen.findByRole("heading", { level: 1, name: "Question 1 of 10" });
    expect(currentRadios().map((r) => r.value)).toEqual(order);
    expect(currentRadios()[3]!.checked).toBe(true);
    expect(fake.calls.filter((c) => c.method === "POST")).toHaveLength(1);
  });

  it("offers Resume on the home page for an in-progress attempt", async () => {
    const first = renderAt("/");
    await startQuiz(first.user, /^Start Week 9,/);
    first.unmount();
    renderAt("/");
    expect(await screen.findByRole("link", { name: /Resume Week 9/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start a new attempt of Week 9/ })).toBeInTheDocument();
  });

  it("shows a recovery message when the access token is missing, without creating an attempt", async () => {
    renderAt("/attempts/att-unknown");
    expect(await screen.findByRole("heading", { name: "This attempt can't be opened" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to quiz selection" })).toBeInTheDocument();
    expect(fake.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("shows a recovery message when the stored token is rejected", async () => {
    const first = renderAt("/");
    await startQuiz(first.user, /^Start Week 10,/);
    const attemptId = [...fake.attempts.keys()][0]!;
    first.unmount();
    attemptStore.save({ ...attemptStore.get(attemptId)!, token: "tampered" });
    renderAt(`/attempts/${attemptId}`);
    expect(await screen.findByRole("heading", { name: "This attempt can't be opened" })).toBeInTheDocument();
  });
});

describe("overall quiz", () => {
  it("contains 120 questions with navigation to the last one", async () => {
    const { user } = renderAt("/");
    await startQuiz(user, /^Start Overall Quiz/);
    expect(fake.calls.find((c) => c.method === "POST")?.body).toEqual({ mode: "overall" });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Question 1 of 120");
    const palette = screen.getByRole("navigation", { name: "Question navigator" });
    expect(within(palette).getAllByRole("button")).toHaveLength(120);
    expect(screen.getByTestId("progress-text")).toHaveTextContent("0 answered · 120 remaining");

    await user.click(currentRadios()[0]!);
    await user.click(screen.getByRole("button", { name: "Question 60, unanswered" }));
    await user.click(currentRadios()[1]!);
    await user.click(screen.getByRole("button", { name: "Question 120, unanswered" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Question 120 of 120");
    await user.click(currentRadios()[2]!);
    await waitFor(() => expect(screen.getByTestId("progress-text")).toHaveTextContent("3 answered · 117 remaining"));

    await user.click(screen.getByRole("button", { name: "Submit quiz" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("dialog-unanswered")).toHaveTextContent("117");
    await user.click(within(dialog).getByRole("button", { name: "Submit quiz" }));
    expect(await screen.findByTestId("score")).toHaveTextContent("/ 120");
    expect(screen.getAllByTestId("review-item")).toHaveLength(120);
    expect(screen.getByRole("navigation", { name: "Jump to question" })).toBeInTheDocument();
  });

  it("never renders correctness hints while the quiz is in progress", async () => {
    const { user } = renderAt("/");
    await startQuiz(user, /^Start Week 11,/);
    await user.click(currentRadios()[0]!);
    await screen.findByText(/Answer saved/);
    const main = screen.getByRole("main");
    expect(main.textContent).not.toMatch(/correct/i);
    expect(main.innerHTML).not.toMatch(/is-correct|badge--correct|review/);
  });
});
