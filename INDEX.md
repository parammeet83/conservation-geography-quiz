# Conservation Geography Quiz — Documentation Index

## Project purpose

Build a browser-based MCQ quiz app from the provided **Conservation Geography — Week 1–12 Assignment Solutions (2026)** PDF. The source contains **120 questions**: 10 questions per week across 12 weeks. Every question has four options, and the correct answer is the option shown in bold/dark black in the source PDF.

The app must provide:

- **12 week-wise quizzes** — each week contains its own 10 questions only.
- **One overall quiz** — all 120 questions, with every question included once.
- **Question shuffling** — question order is randomized for every new attempt.
- **Option shuffling** — the four options are randomized independently for every question in both quiz modes.
- **Stable correctness** — the correct answer stays associated with the correct option ID after shuffling; it must never depend on the source letter or the displayed A/B/C/D label.
- **Safe answer handling** — the API must not reveal correct-answer flags before submission.
- **Attempt consistency** — a refresh/resume continues the same saved question and option order; it must not reshuffle an attempt already in progress.

## File map

| File | Purpose |
|---|---|
| [`PRD.md`](PRD.md) | Product scope, user stories, functional/non-functional requirements, and acceptance criteria. |
| [`TRD.md`](TRD.md) | Proposed stack, architecture, shuffle/grading algorithms, API contract, seed-data rules, and PDF-derived answer audit. |
| [`Backend_DB_Schema.md`](Backend_DB_Schema.md) | Relational model and PostgreSQL DDL for questions, options, quiz attempts, randomized display order, and answers. |
| [`UIUX_design_spec.md`](UIUX_design_spec.md) | Screens, states, layout, interactions, accessibility, and responsive behavior. |
| [`WebAppFlow.md`](WebAppFlow.md) | User navigation and main runtime sequences, including quiz submission. |
| [`implementation_plan.md`](implementation_plan.md) | Ordered implementation tasks and quality gates. |
| [`README.md`](README.md) | As-built overview: features, stack, architecture, setup, API, testing, troubleshooting. |
| [`docs/RUN_AND_VERIFY.md`](docs/RUN_AND_VERIFY.md) | Windows/PowerShell guide to run and verify every behaviour. |
| [`data/seed/`](data/seed/) | Validated question bank (`questions.json`), answer-key audit (`answer_key_audit.csv`), import report, manual visual review. |

## Decisions and assumptions

- **Stack (implemented):** React + TypeScript + Vite frontend; FastAPI + Python backend; PostgreSQL; SQLAlchemy 2.x/Alembic; pytest for backend tests; Vitest/React Testing Library for frontend tests; Playwright for end-to-end tests.
- **MVP access model:** no account system required. Attempts use an opaque attempt ID plus an access token or equivalent ownership check. Do not expose an attempt solely because an attacker guesses a sequential ID.
- **Scoring default:** one point for each correct answer, zero for incorrect or unanswered, no negative marking. Weekly maximum = 10; overall maximum = 120. Keep this rule easy to change.
- **Feedback default:** show the score and correct answers after submission. Do not reveal correctness while the attempt is in progress.
- **Source fidelity:** retain the question and option wording from the PDF. Do not add explanations or silently alter an answer. If any source entry is ambiguous, log it for review.
- **No runtime PDF dependency:** parse/verify the PDF during data preparation; the running app should read the validated database records, not re-parse a PDF on every request.

## Critical build rule

Never randomize only the visible labels while grading against original A/B/C/D positions. Persist IDs and attempt-specific display order, then grade by the selected **option ID** on the server.

## Definition of done

The project is not complete until all 120 questions are loaded, each week has exactly 10 questions, each question has exactly four options and exactly one correct option, both quiz modes pass automated coverage tests, and repeated/new attempts demonstrate the required shuffling without changing the answer key.
