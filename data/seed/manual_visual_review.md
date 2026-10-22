# Manual Visual Review of the Answer Key

- **Date:** 2026-10-22
- **Source:** `Conservation Geography Week 1 Solutions-merged.pdf` (26 pages, SHA-256 `3c5d1b1c86e09fc24afb380e7e1952e8a6f3813d0abfedae6919e3e5db72d7b5`)
- **Method:** all 26 pages were rendered to images (PyMuPDF, 1.1x zoom, two pages per image) and inspected visually. For each question, the option shown in bold/dark black on the rendered page was compared with the `is_correct` option in `questions.json` (listed as week, question number, page, source label, and option text).

## Result

| Pages | Questions reviewed | Discrepancies |
|---|---|---:|
| 1–2 | Week 1 Q1–Q10 | 0 |
| 3–4 | Week 2 Q1–Q10 | 0 |
| 5–7 | Week 3 Q1–Q10 (Q5, Q10 continue onto the next page) | 0 |
| 8–10 | Week 4 Q1–Q10 (Q5, Q10 continue onto the next page) | 0 |
| 11–12 | Week 5 Q1–Q10 (Q5 continues onto page 12) | 0 |
| 13–14 | Week 6 Q1–Q10 (Q5 continues onto page 14) | 0 |
| 15–16 | Week 7 Q1–Q10 | 0 |
| 17–18 | Week 8 Q1–Q10 | 0 |
| 19–20 | Week 9 Q1–Q10 | 0 |
| 21–22 | Week 10 Q1–Q10 (Q5 continues onto page 22) | 0 |
| 23–24 | Week 11 Q1–Q10 | 0 |
| 25–26 | Week 12 Q1–Q10 (Q5 continues onto page 26) | 0 |

Every question shows exactly one visibly bold option, and it is the option recorded as correct in the seed data. 120 of 120 answers agree.

## Observations (no change made)

- W3 Q6's bold option wraps over two lines; the extracted text joins both lines.
- W1 Q3, W1 Q10 (a, b), and W4 Q10 place the option text on the same line as the label; these were extracted correctly.
- The PDF uses `a.` labels for some questions in Weeks 7, 8, and 12; labels are import metadata only.
- Identical question stems appear in W3 Q2 / W7 Q9, W6 Q7 / W6 Q10, and W11 Q4 / W11 Q5. They are distinct source questions (different week or different options) and are kept as separate records.
- Source wording, spelling, and marked answers are preserved exactly; no answer was changed based on outside knowledge.
