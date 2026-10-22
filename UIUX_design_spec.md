# UI/UX Design Specification

## 1. Design goals

The interface should be a study tool, not a feature-heavy learning-management system. Users should understand quiz scope, progress, and submission state immediately. Avoid animations or decoration that slow navigation through a 120-question test.

## 2. Information architecture

1. **Home / Quiz selection**
   - Page title: “Conservation Geography Quiz”
   - Short helper text: “Choose a week to practice or take the full 120-question test.”
   - Twelve week cards, labelled Week 1 through Week 12; each shows “10 questions”.
   - One visually distinct but not oversized Overall Quiz card; shows “120 questions”.
2. **Active quiz**
   - Quiz name and scope (Week N or Overall Quiz).
   - Current question number and total (e.g. `Question 4 of 10` or `Question 4 of 120`).
   - Progress indicator and answered/remaining counts.
   - Question text, four radio-style options, Previous/Next controls, question navigator, Save/Submit controls.
3. **Submit confirmation**
   - Summarizes answered and unanswered counts.
   - Warns that submission is final for that attempt.
   - Allows the user to go back instead of submitting.
4. **Results / answer review**
   - Correct count, incorrect count, unanswered count, score percentage.
   - Per-question review with selected answer, correct answer, and status.
   - “Back to quiz selection” and “Try again” actions. “Try again” creates a fresh shuffled attempt.

## 3. Home page layout

- Use a clean neutral background and a centered content column.
- On desktop, show week cards in a 3–4 column grid depending on available width; place the overall quiz prominently above or beside the grid.
- On mobile, stack the cards in one column or use a compact two-column layout only if the labels remain readable.
- Each week card is one large click target, with the number and question count clearly readable.
- Do not show a “score” on a week card unless saved history is actually implemented. Do not imply progress tracking that does not exist.

## 4. Active quiz layout

### Header

- Left: quiz scope/title.
- Main line: `Question X of N`.
- Progress bar plus text such as `6 answered · 4 remaining`.
- On narrow screens, allow the title and progress to wrap naturally rather than shrink text excessively.

### Question panel

- Display the complete question text with preserved paragraph/line breaks where meaningful.
- Show exactly four options in the order returned by the backend.
- Each option is a labelled radio control with a large clickable row.
- Display labels A, B, C, D based on the shuffled presentation; never show source labels from the PDF as a correctness cue.
- Maintain a visible selected state. Do not use green/red correctness colors before submission.
- Long option text must wrap without clipping.

### Navigation

- Previous and Next buttons should be consistently placed.
- Disable Previous on the first question and Next on the last question, unless Next is replaced by Submit on the last question.
- Provide a compact question palette: unanswered, answered, and current states must be distinct without relying on color alone. Clicking a number navigates to that question.
- On mobile, the palette can be a collapsible drawer or horizontal, scrollable navigator with an accessible label.
- Selecting an option triggers a save. The interface must show saving/saved/error feedback or otherwise make failed persistence clear.

### Submission

- Do not submit just because the user reaches the final question.
- On submit click, show counts for answered and unanswered questions.
- If unanswered questions exist, phrase the dialog neutrally: “You have X unanswered questions. Submit anyway?”
- Provide explicit “Review answers” and “Submit quiz” actions.
- Disable repeated submit clicks while the request is processing.

## 5. Results screen

- Use a clear score summary near the top: `Correct / Total`, percentage, incorrect, unanswered.
- Use the same scoring convention as the backend: one point per correct answer, no negative marking, unanswered = zero.
- In the review list, each question shows its text, the chosen answer or `Not answered`, and the correct answer.
- Only after submission, use text and icon/label together for states such as Correct, Incorrect, and Unanswered; do not rely on color alone.
- Long 120-question reviews should support jump links and optionally collapsed answer rows so the screen remains navigable.
- Do not invent an explanation section; the source PDF only supplies questions, options, and marked correct options.

## 6. Visual direction

- Tone: academic, calm, high contrast.
- Typography: readable sans serif; base text about 16 px; question text about 18–20 px on desktop and at least 16 px on small screens.
- Use consistent spacing and clear hierarchy rather than gradients and heavy shadows.
- Primary action: a solid, high-contrast button. Secondary actions: outlined or neutral buttons.
- Error and unsaved states must be visible and understandable.
- Avoid a visual distinction that makes one displayed option look like the correct option before submission.

## 7. Responsive breakpoints (guidelines)

- Small mobile: up to 480 px — one-column content, full-width navigation buttons, compact/collapsible question palette.
- Tablet: 481–900 px — two-column home cards; question panel remains single-column.
- Desktop: above 900 px — three or four home-card columns; quiz question uses a readable max-width; optional navigator side panel.

These are design guidelines, not hard dependencies on a specific CSS framework.

## 8. Accessibility

- Use semantic headings and buttons.
- Use a `fieldset` and `legend` (or equivalent semantic grouping) for options; every option must have an associated label.
- Entire option rows should work with pointer, keyboard, and assistive technology.
- Maintain visible focus indicators and logical tab order.
- Provide adequate contrast, do not communicate state using color alone, and ensure controls meet comfortable touch-target sizes.
- Announce question changes and save status to screen readers without interrupting excessively.
- Progress indicator should have an accessible name and numeric progress text.
- Confirm dialog focus must remain trapped when modal and return to the submit button when closed.

## 9. UI state model

- `loading`: obtaining catalogue/attempt.
- `in_progress`: question and options loaded, answers editable.
- `saving`: answer update pending.
- `save_error`: show retry or reconnect guidance and do not claim the answer was saved.
- `submitting`: controls temporarily disabled.
- `submitted`: immutable attempt; show result/review.
- `load_error`: show retry action and safe exit to home.

## 10. Implementation notes (as built)

- The question palette sits in a side panel on desktop and in a collapsible "Go to question" section on narrow screens (open by default for 10-question quizzes). Answered = filled with a check mark, unanswered = outlined, current = thick ring plus `aria-current`, not saved = dashed border with "!".
- Selecting an option saves immediately; the footer shows *Saving...*, *Answer saved*, or *Not saved ... Retry*. The confirmation dialog blocks submission while any answer is unsaved and offers *Retry saving*.
- The confirmation dialog is a custom modal with a focus trap; Escape or *Review answers* closes it and focus returns to the Submit button.
- The results review has filter chips (All / Incorrect / Unanswered / Correct), jump links for quizzes longer than 10 questions, and a collapsible "Show all options" list per question.
- Light and dark colour schemes follow the operating-system preference.

## 11. UX acceptance checks

- A user can identify and start any week and the overall quiz.
- All options remain readable after shuffling and on mobile.
- Refresh does not change the order of an existing attempt.
- The user can identify unanswered questions before submission.
- Results make selected vs correct answers explicit without ambiguity.
- The active quiz does not visually or programmatically reveal which option is correct.
