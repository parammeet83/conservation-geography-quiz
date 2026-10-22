# Implementation Plan

> **Status (2026-10-22):** all phases implemented and verified locally; see README.md and docs/RUN_AND_VERIFY.md. The PDF was kept local (not committed) because the target repository is public.

## Guiding rule

Finish content integrity and answer-key verification before polishing the interface. A visually finished quiz with even one mis-keyed option is not acceptable.

## Phase 0 — Repository and project setup

- [x] Create a clean repo layout for `frontend/`, `backend/`, `data/source/`, `data/seed/`, and `docs/` (or use the existing project structure without duplicating folders).
- [x] Add `.gitignore` for virtual environments, `node_modules`, build outputs, environment files, logs, and local database volumes.
- [x] Add `.env.example` with placeholders only; do not commit credentials.
- [x] Record the proposed stack and development commands in the project README.
- [x] Put the source PDF in the documented local source path; decide whether the PDF may be committed based on ownership/distribution rights.

**Exit gate:** frontend and backend start locally, and no secrets or large runtime artifacts are accidentally tracked.

## Phase 1 — PDF extraction and question-bank verification

- [x] Build a repeatable extraction/import script or curated seed file to capture week, question number, question text, four options, original labels, page number, and font/bold information.
- [x] Handle questions/options that wrap over multiple lines or cross a PDF page break.
- [x] Normalize option labels (`(a)` and `a.` become the same import concept) while preserving the original option text.
- [x] Mark the option styled bold/dark black in the PDF as correct; store correctness on its stable option record.
- [x] Compare every imported question against the source PDF; do not rely only on text extraction for wrapped lines.
- [x] Generate an import audit report with row counts, per-week counts, four-option checks, one-correct-option checks, and any flagged duplicates/ambiguities.
- [x] Match the bold answer text against the PDF-derived audit table in `TRD.md`.
- [x] Confirm the data is exactly 120 questions, 10 in each of 12 weeks, four options per question, and one correct option per question.

**Exit gate:** seed validation is green. No unresolved import exception is allowed into the initial release.

## Phase 2 — Database and seed workflow

- [x] Create PostgreSQL development/test databases.
- [x] Implement SQLAlchemy models using `Backend_DB_Schema.md`.
- [x] Add Alembic migrations for tables, indexes, checks, and foreign keys.
- [x] Implement an idempotent seed/import command; decide how updated source versions are reconciled without duplicating data.
- [x] Add content-validation command runnable locally and in CI.
- [x] Add integration tests to verify 12 weeks × 10 questions, four options each, and exactly one correct option per question.

**Exit gate:** fresh database migration + seed completes with 120 valid questions and can be repeated without duplication.

## Phase 3 — Backend quiz API

- [x] Implement `GET /api/v1/health` and `GET /api/v1/quizzes`.
- [x] Implement `POST /api/v1/attempts` for weekly and overall modes.
- [x] Implement server-side question shuffle and independent per-question option shuffle.
- [x] Persist both permutations in one transaction.
- [x] Implement attempt access token creation, secure validation, and safe logging.
- [x] Implement `GET /api/v1/attempts/{id}` with correct-answer data excluded while in progress.
- [x] Implement answer save/clear endpoint with same-question option validation.
- [x] Implement transactional, idempotent submit and grading endpoint.
- [x] Implement submitted-only result review endpoint.
- [x] Standardize API errors and validation responses.

**Exit gate:** backend integration tests prove all invariants and active-attempt responses cannot leak the answer key.

## Phase 4 — Frontend core UI

- [x] Build Home/Quiz Selection with 12 week cards and the overall quiz card.
- [x] Build typed API client and request/error states.
- [x] Build Active Quiz: question text, four shuffled options, progress, answered count, previous/next, question palette, submit action.
- [x] Send option IDs from selections; never grade client-side.
- [x] Preserve answers when navigating among questions.
- [x] Add refresh/resume behavior using the saved attempt identity and access token approach chosen in the security design.
- [x] Build submit confirmation with unanswered count.
- [x] Build results summary and answer review.
- [x] Make all pages responsive and keyboard accessible.

**Exit gate:** users can complete a weekly quiz and an overall quiz end-to-end through the browser.

## Phase 5 — Test and harden

- [x] Unit-test Fisher–Yates/shuffle behavior for no loss or duplication of IDs.
- [x] Test grading when the correct answer appears at every one of the four displayed option positions.
- [x] Test weekly scopes for all 12 week numbers.
- [x] Test overall attempt includes each question exactly once.
- [x] Test reload/resume keeps the same question and option ordering.
- [x] Test unanswered questions, save failure, invalid/cross-question option IDs, and attempts in invalid states.
- [x] Test duplicate submits and concurrent/double-click submission.
- [x] Test that no active API payload exposes `is_correct`, correct option IDs, or correct answer text via a hidden field.
- [x] Add one browser-based weekly journey and one full overall journey.
- [x] Check small viewport, focus behavior, contrast, and screen-reader labels.

**Exit gate:** all tests pass against a test database; no critical answer-leakage or scoring bug remains.

## Phase 6 — Delivery and documentation

- [x] Add start commands for frontend, backend, database, migrations, seed, and tests.
- [x] Document environment variables and provide `.env.example`.
- [x] Add CI steps: lint/type-check, unit tests, database-backed integration tests, migration, seed validation.
- [x] Verify production CORS/origin settings and database persistence.
- [x] Perform the release checklist below.

## Release checklist

- [x] Source PDF import is versioned and auditable.
- [x] 120 questions total and 10 in each week.
- [x] Four options and one correct option on every question.
- [x] All correct options map to the PDF bold formatting.
- [x] Week-wise attempts include only the selected week.
- [x] Overall attempts include all 120 questions exactly once.
- [x] Question and option orders shuffle on new attempts.
- [x] Existing attempts keep their original saved order after refresh.
- [x] Correct-answer data is private until submission.
- [x] Server-side scoring and result review match the selected option IDs.
- [x] Error states do not silently lose selected answers.
- [x] Docs and commands match the actual implementation.

## Suggested build order

Do not build all frontend screens first. The correct sequence is **validated question bank → database invariants → attempt/shuffle/grading API → frontend flow → browser QA**. That order reduces the risk of rewriting the app after discovering the PDF import or answer key is wrong.
