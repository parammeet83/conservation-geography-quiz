# Product Requirements Document (PRD)

## 1. Product summary

**Product name:** Conservation Geography Quiz

**Problem:** The learner needs a convenient way to practice 12 weeks of Conservation Geography MCQs individually by week and then take one cumulative test containing all 120 questions. Printed/PDF answer positions are not suitable for a quiz app because the order of questions and choices must change on each new attempt.

**Product goal:** Convert the supplied Week 1–12 assignment-solutions PDF into a reliable web quiz with week-wise practice, a cumulative test, randomized questions and randomized options, saved attempt state, and post-submission results.

## 2. Source of truth

- Source file: `Conservation Geography Week 1 Solutions-merged.pdf` (26 pages, SHA-256 `3c5d1b1c…d72d7b5`). The PDF is a local data-preparation input and is not committed to the public repository; the validated seed files in `data/seed/` are derived from it.
- Expected content: 12 week sections, 10 questions per section, 120 questions total.
- Each item is an MCQ with four options.
- The correct option is the option formatted in bold/dark black in the PDF.
- Preserve source wording, including technical terminology and spelling, unless a transcription issue is explicitly reviewed and logged.
- The PDF may use `(a)` labels in some weeks and `a.` labels in others. These labels are input metadata only. The app generates fresh display labels after shuffling.

The PDF is authoritative for this project’s answer key. Do not replace its marked answer with a guessed or internet-derived answer. If a potential source mistake is found, record it in a review note and obtain an explicit decision before changing the key.

## 3. Target user and primary job

**Primary user:** A student preparing for a Conservation Geography assessment.

**Primary job:** Choose a week to revise, answer 10 randomized MCQs, submit and review the result; later take a full 120-question assessment across all weeks.

Authentication, public leaderboards, teacher dashboards, and multi-course support are not required for the MVP.

## 4. Scope

### In scope

1. Landing page showing Week 1 through Week 12 and an Overall Quiz entry.
2. Week cards show week number, question count, and attempt/start action.
3. Week-wise quiz always contains the 10 questions assigned to that week and no questions from other weeks.
4. Overall quiz contains all 120 questions exactly once per attempt.
5. Randomize question order for every new attempt.
6. Randomize each question’s four options separately for every new attempt.
7. Render new option labels (A, B, C, D) based on the shuffled order; labels are not identifiers.
8. Previous/Next navigation, question palette or equivalent question-jump navigation, answered/unanswered state, and progress count.
9. Save selected answers and attempt-specific display order so refresh/re-entry does not alter an in-progress attempt.
10. Submit confirmation, server-side grading, score summary, and post-submit answer review.
11. Show correct answer and the user's selected answer after submission, including unanswered questions.
12. Responsive desktop, tablet, and mobile layouts.
13. Seed/import validation and automated tests for counts, answer integrity, and shuffle behavior.

### Out of scope for MVP

- User accounts and password reset.
- Timed examinations, negative marking, question explanations, hints, bookmarks, leaderboards, and certificates.
- Editing questions from the UI.
- Automatic AI-generated questions or explanations.
- Runtime PDF parsing in the deployed web app.

These can be added only as separate requirements, not slipped into the initial build.

## 5. Core user stories

- As a learner, I can see all 12 weeks and the overall quiz so I can select the scope I want to practice.
- As a learner, I can start Week N and receive exactly its 10 questions.
- As a learner, I can start the overall quiz and receive all 120 questions exactly once.
- As a learner, I see the questions in randomized order on each new attempt.
- As a learner, I see the four choices for each question in randomized order, independently of the question order.
- As a learner, I can navigate back and forth without losing selected answers.
- As a learner, I can refresh or resume an in-progress attempt without the saved order changing.
- As a learner, I can submit the quiz and see an accurate score and answer review.
- As a maintainer, I can verify that imported questions match the PDF’s bolded correct options before release.

## 6. Functional requirements

### FR-01 — Quiz catalogue

The app must list 12 weeks. Every week must display `10 questions`. The overall quiz must display `120 questions`. Availability is based on validated seed data, not hard-coded counts alone.

### FR-02 — Week-wise attempt creation

When a learner starts Week N, the server selects the 10 active questions for that week, randomizes their order, randomizes each question’s options, persists both orders, and creates one in-progress attempt.

### FR-03 — Overall attempt creation

When the learner starts the overall quiz, the server includes all 120 active questions once, randomizes their order, randomizes each question’s four options, persists the orders, and creates one in-progress attempt. It must not sample 10 or otherwise omit questions.

### FR-04 — Option correctness

Every option has a stable database ID. The correct option is marked in the database by a boolean or equivalent stable reference, established from the PDF’s bold formatting. Correctness must never be derived from option position, original letter, display label, or client-side array index.

### FR-05 — Answer selection and progress

A learner can select one answer per question or leave it unanswered. The UI shows total answered and remaining questions. Answer updates must be persisted through the backend.

### FR-06 — Resume behavior

Loading an existing attempt returns the stored question sequence and option sequence. The backend must not regenerate these sequences during reload, navigation, or ordinary GET requests.

### FR-07 — Submission and scoring

Submission is idempotent: a second submit must not create a second result or change a submitted attempt. The backend grades stored selected option IDs against the correct options in one transaction. Default score is `correct_count / total_questions * 100`; unanswered and incorrect answers score zero. Round percentage to two decimal places for display.

### FR-08 — Results and review

Show quiz mode/week, number correct, incorrect, unanswered, score percentage, and a question-by-question review. For every item show the question, the selected answer or “Not answered”, and the PDF-derived correct answer. Correct-answer data is returned only after the attempt is submitted.

### FR-09 — Content validation

Before deployment, automated validation must fail if there are not exactly 120 active questions, any week does not contain exactly 10, any question does not have exactly four options, or a question has other than one correct option.

### FR-10 — Error states

Provide understandable messages for failed creation, save, resume, and submission. A failed save must not silently appear successful. Preserve local in-memory selections while retrying; show a clear unsaved/error indicator when persistence is unavailable.

## 7. Non-functional requirements

- **Correctness:** 100% of question/answer relationships must remain valid under all shuffles.
- **Performance:** normal catalogue and question-navigation requests should feel immediate; target API response under 500 ms at the 95th percentile on a modest deployment for this small dataset, excluding cold starts.
- **Reliability:** submission and grading use a database transaction; duplicate submit requests are safe.
- **Security:** never send `is_correct` during an active attempt. Validate that an attempt token grants access to that attempt. Do not trust client-supplied scores or correctness.
- **Accessibility:** keyboard-operable controls, visible focus, semantic labels, sufficient contrast, and screen-reader announcements for state changes.
- **Responsive behavior:** usable at 360 px viewport width without horizontal scrolling of the page.
- **Maintainability:** separate question-bank content from UI code; keep business logic and grading on the backend.

## 8. UX and scoring defaults

- No timer for MVP.
- One point per correct answer; no negative marking.
- Submission is explicit and requires confirmation if the attempt has unanswered questions.
- Correct answers and score appear after submission only.
- Starting another attempt creates a new shuffled order. Resuming an existing attempt preserves its order.

These are proposed defaults where the request did not define behavior.

## 9. Acceptance criteria

1. The catalogue shows Week 1–Week 12 and Overall Quiz.
2. Each week launches exactly the 10 questions whose source week matches that week.
3. Overall quiz has 120 distinct question IDs; no duplicate or missing question exists in the attempt.
4. Every question presents exactly four options.
5. For every new attempt, question and option orders are generated server-side and stored.
6. On reload, the same attempt returns the same question and option order.
7. The correct answer stays correct after any shuffle.
8. The active-attempt API payload contains no correctness flag or correct option ID.
9. Submission computes the score on the server and shows a review based on source-derived answer keys.
10. Automated seed checks pass for 120 questions, 10 per week, 4 options and exactly 1 correct option per question.
11. Tests cover both quiz modes, unanswered answers, invalid option IDs, duplicate submissions, refresh/resume, and option shuffling.

## 10. Success measures

- Seed validation: 120/120 questions pass structural checks.
- Coverage: 12/12 weekly quiz scopes and the overall quiz pass automated integration tests.
- Integrity: zero scoring mismatches in a test suite that places the correct option in each of the four display positions.
- Usability: a learner can start, complete, submit, and review either quiz mode without instructions from a developer.
