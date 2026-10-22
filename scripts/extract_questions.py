"""Extract the Conservation Geography question bank from the source PDF.

This is a maintainer-only data-preparation tool. The running application never
reads the PDF; it reads the validated seed files written by this script.

Usage (from the repository root):

    python scripts/extract_questions.py --pdf "Conservation Geography Week 1 Solutions-merged.pdf"

Outputs:
    data/seed/questions.json
    data/seed/answer_key_audit.csv
    data/seed/import_validation_report.md

Correct answers are determined from the PDF itself, using two independent signals:

1. Font metadata: the option text is set in a bold font (``Calibri,Bold``).
2. Rendered page: the option's rasterised glyphs have clearly thicker strokes
   than the other options of the same question (bold = "dark black").

Both signals must agree, and the result is cross-checked against the answer-key
audit table in TRD.md. Any disagreement, partial bolding, missing option, or
count mismatch is recorded as an unresolved issue and the script exits non-zero.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = REPO_ROOT / "data" / "seed"
DEFAULT_PDF = REPO_ROOT / "Conservation Geography Week 1 Solutions-merged.pdf"
TRD_PATH = REPO_ROOT / "TRD.md"

# Stable identifiers: the same (week, question, source label) always maps to the
# same UUID, which keeps seeding idempotent and IDs stable across re-imports.
ID_NAMESPACE = uuid.UUID("6f1d2c1e-6a43-4f53-9a43-6c0a3f1f8a51")

EXPECTED_WEEKS = 12
EXPECTED_PER_WEEK = 10
LABELS = ("a", "b", "c", "d")

WEEK_HEADER_RE = re.compile(r"^Week\s+(\d{1,2})\s+Assignment Solutions", re.I)
TITLE_RE = re.compile(r"^Conservation Geography\s*$", re.I)
Q_INLINE_RE = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")  # "1. Question text"
Q_BARE_RE = re.compile(r"^(\d{1,2})$")  # "1" on its own line
OPT_PAREN_RE = re.compile(r"^\(([a-d])\)\s*(.*)$")  # "(a) text" or "(a)"
OPT_DOT_RE = re.compile(r"^([a-d])\.\s*(.*)$")  # "a. text" or "a."

RENDER_ZOOM = 4.0
INK_THRESHOLD = 128  # grey level below which a pixel counts as ink
# A bold option's mean rendered stroke width must exceed that of the heaviest
# non-bold option of the same question by at least this factor.
INK_MARGIN = 1.15


def question_uuid(week: int, qno: int) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, f"cgq:w{week}:q{qno}"))


def option_uuid(week: int, qno: int, label: str) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, f"cgq:w{week}:q{qno}:{label}"))


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def norm_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return clean(text).casefold()


@dataclass
class Span:
    text: str
    bold: bool
    font: str
    page: int
    bbox: tuple[float, float, float, float]
    char_boxes: tuple = ()  # one (x0, y0, x1, y1) per character of ``text``


@dataclass
class Line:
    spans: list[Span]
    page: int

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)


@dataclass
class OptionDraft:
    label: str
    label_style: str
    page: int
    spans: list[Span] = field(default_factory=list)

    @property
    def text(self) -> str:
        return clean("".join(s.text for s in self.spans))

    def bold_ratio(self) -> float:
        total = sum(len(s.text.replace(" ", "")) for s in self.spans)
        bold = sum(len(s.text.replace(" ", "")) for s in self.spans if s.bold)
        return bold / total if total else 0.0


@dataclass
class QuestionDraft:
    week: int
    qno: int
    page: int
    numbering_style: str
    text_spans: list[Span] = field(default_factory=list)
    options: list[OptionDraft] = field(default_factory=list)

    @property
    def text(self) -> str:
        return clean("".join(s.text for s in self.text_spans))


def read_lines(doc: fitz.Document) -> list[Line]:
    lines: list[Line] = []
    for page_index, page in enumerate(doc):
        for block in page.get_text("rawdict")["blocks"]:
            for raw_line in block.get("lines", []):
                spans = [
                    Span(
                        text="".join(c["c"] for c in s["chars"]),
                        bold=bool(s["flags"] & 16) or "bold" in s["font"].lower(),
                        font=s["font"],
                        page=page_index + 1,
                        bbox=tuple(s["bbox"]),
                        char_boxes=tuple(tuple(c["bbox"]) for c in s["chars"]),
                    )
                    for s in raw_line["spans"]
                ]
                line = Line(spans=spans, page=page_index + 1)
                if line.text.strip():
                    lines.append(line)
    return lines


def split_after_label(line: Line, label_len: int) -> list[Span]:
    """Return the spans of ``line`` that follow its first ``label_len`` characters."""
    out: list[Span] = []
    consumed = 0
    stripped_leading = len(line.text) - len(line.text.lstrip())
    skip = stripped_leading + label_len
    for span in line.spans:
        if consumed + len(span.text) <= skip:
            consumed += len(span.text)
            continue
        offset = max(0, skip - consumed)
        consumed += len(span.text)
        out.append(
            Span(span.text[offset:], span.bold, span.font, span.page, span.bbox, span.char_boxes[offset:])
        )
    return [s for s in out if s.text]


def parse(lines: list[Line], issues: list[str]) -> list[QuestionDraft]:
    questions: list[QuestionDraft] = []
    week: int | None = None
    current: QuestionDraft | None = None
    current_opt: OptionDraft | None = None
    in_question_text = False

    def close_question() -> None:
        nonlocal current, current_opt
        if current is not None:
            questions.append(current)
        current, current_opt = None, None

    for line in lines:
        text = line.text.strip()
        if TITLE_RE.match(text):
            continue
        header = WEEK_HEADER_RE.match(text)
        if header:
            close_question()
            week = int(header.group(1))
            continue
        if week is None:
            issues.append(f"Text before first week header on page {line.page}: {text!r}")
            continue

        expected_next = (current.qno + 1) if current else 1
        inline_q = Q_INLINE_RE.match(text)
        bare_q = Q_BARE_RE.match(text)
        # A number only starts a new question when it is the next expected number
        # and the previous question already has all four options. This prevents
        # option text such as "30 years" or "1500 m" being mistaken for numbering.
        ready_for_next = current is None or len(current.options) == 4
        if (inline_q or bare_q) and ready_for_next:
            qno = int((inline_q or bare_q).group(1))
            if qno == expected_next:
                close_question()
                current = QuestionDraft(
                    week=week,
                    qno=qno,
                    page=line.page,
                    numbering_style="inline" if inline_q else "bare",
                )
                if inline_q:
                    current.text_spans.extend(split_after_label(line, len(inline_q.group(1)) + 1))
                in_question_text = True
                continue

        opt = OPT_PAREN_RE.match(text) or OPT_DOT_RE.match(text)
        if opt and current is not None:
            label = opt.group(1)
            expected_label = LABELS[len(current.options)] if len(current.options) < 4 else None
            if label == expected_label:
                style = "(a)" if text.startswith("(") else "a."
                label_len = 3 if style == "(a)" else 2
                current_opt = OptionDraft(label=label, label_style=style, page=line.page)
                current_opt.spans.extend(split_after_label(line, label_len))
                current.options.append(current_opt)
                in_question_text = False
                continue

        if current is None:
            issues.append(f"Week {week}: orphan text on page {line.page}: {text!r}")
            continue
        if in_question_text:
            if current.text_spans:
                current.text_spans.append(Span(" ", False, "", line.page, line.spans[0].bbox))
            current.text_spans.extend(line.spans)
        elif current_opt is not None:
            if current_opt.spans:
                current_opt.spans.append(Span(" ", current_opt.spans[-1].bold, "", line.page, line.spans[0].bbox))
            current_opt.spans.extend(line.spans)
        else:
            issues.append(f"W{week} Q{current.qno}: unassigned text on page {line.page}: {text!r}")

    close_question()
    return questions


def stroke_width(doc: fitz.Document, spans: list[Span], cache: dict) -> float:
    """Estimate rendered stroke weight of the option's glyphs.

    Each non-space character's box is rasterised; the mean length of horizontal
    runs of dark pixels approximates stem thickness. Bold ("dark black") text has
    visibly thicker stems than regular text, independent of which letters appear.
    """
    total_len = 0
    runs = 0
    for s in spans:
        if not s.font:
            continue
        if s.page not in cache:
            pix = doc[s.page - 1].get_pixmap(matrix=fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM), colorspace=fitz.csGRAY)
            # Pixmap.samples returns a fresh copy on every access, so keep one.
            cache[s.page] = (bytes(pix.samples), pix.stride, pix.width, pix.height)
        samples, stride, width, height = cache[s.page]
        for ch, box in zip(s.text, s.char_boxes):
            if not ch.strip():
                continue
            x0, y0, x1, y1 = (int(round(v * RENDER_ZOOM)) for v in box)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(width, x1), min(height, y1)
            for y in range(y0, y1):
                row = samples[y * stride + x0 : y * stride + x1]
                run = 0
                for v in row:
                    if v < INK_THRESHOLD:
                        run += 1
                    elif run:
                        total_len += run
                        runs += 1
                        run = 0
                if run:
                    total_len += run
                    runs += 1
    return total_len / runs if runs else 0.0


def load_trd_key(path: Path) -> dict[tuple[int, int], str]:
    key: dict[tuple[int, int], str] = {}
    if not path.exists():
        return key
    week = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^###\s+Week\s+(\d+)\s*$", raw.strip())
        if m:
            week = int(m.group(1))
            continue
        m = re.match(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*$", raw.strip())
        if m and week is not None:
            key[(week, int(m.group(1)))] = m.group(2)
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--trd", type=Path, default=TRD_PATH)
    parser.add_argument("--out", type=Path, default=SEED_DIR)
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"ERROR: source PDF not found: {args.pdf}", file=sys.stderr)
        return 2

    pdf_bytes = args.pdf.read_bytes()
    checksum = hashlib.sha256(pdf_bytes).hexdigest()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    issues: list[str] = []
    lines = read_lines(doc)
    drafts = parse(lines, issues)
    trd_key = load_trd_key(args.trd)
    if not trd_key:
        issues.append(f"TRD answer-key table not found or empty at {args.trd}")

    render_cache: dict = {}
    # The manual review record only counts if it names this exact PDF.
    review_file = args.out / "manual_visual_review.md"
    visually_reviewed = review_file.exists() and checksum in review_file.read_text(encoding="utf-8")
    questions_out = []
    audit_rows = []
    seen: set[tuple[int, int]] = set()

    for q in drafts:
        ident = (q.week, q.qno)
        q_issues: list[str] = []
        notes: list[str] = []
        if ident in seen:
            q_issues.append("duplicate (week, question_number)")
        seen.add(ident)
        if not q.text:
            q_issues.append("blank question text")
        if any(s.bold for s in q.text_spans if s.text.strip()):
            q_issues.append("question text contains bold characters")
        if len(q.options) != 4:
            q_issues.append(f"expected 4 options, found {len(q.options)}")

        ratios = [o.bold_ratio() for o in q.options]
        inks = [stroke_width(doc, o.spans, render_cache) for o in q.options]
        bold_idx = [i for i, r in enumerate(ratios) if r == 1.0]
        partial_idx = [i for i, r in enumerate(ratios) if 0.0 < r < 1.0]
        for i in partial_idx:
            q_issues.append(f"option ({q.options[i].label}) is only partially bold ({ratios[i]:.0%})")
        if len(bold_idx) != 1:
            q_issues.append(f"expected exactly 1 bold option, found {len(bold_idx)}")
        for o in q.options:
            if not o.text:
                q_issues.append(f"option ({o.label}) is blank")
        texts = [norm_for_match(o.text) for o in q.options]
        if len(set(texts)) != len(texts):
            q_issues.append("duplicate option text within question")

        font_check = render_check = trd_check = "n/a"
        correct_text = ""
        if len(bold_idx) == 1:
            ci = bold_idx[0]
            correct_text = q.options[ci].text
            font_check = "pass"
            others = [v for i, v in enumerate(inks) if i != ci]
            ratio = inks[ci] / max(others) if others and max(others) else float("inf")
            render_check = "pass" if ratio >= INK_MARGIN else "fail"
            if render_check == "fail":
                q_issues.append(f"rendered stroke-weight check failed (bold/max-other ratio {ratio:.2f})")
            notes.append(f"render stroke ratio {ratio:.2f}")
            expected = trd_key.get(ident)
            if expected is None:
                trd_check = "missing"
                q_issues.append("no TRD audit entry")
            elif norm_for_match(expected) == norm_for_match(correct_text):
                trd_check = "pass"
            else:
                trd_check = "fail"
                q_issues.append(f"TRD audit mismatch: TRD={expected!r} PDF={correct_text!r}")

        status = "verified" if not q_issues else "unresolved"
        if q.options and len({o.label_style for o in q.options}) > 1:
            notes.append("mixed option label styles")
        pages = sorted({q.page, *(o.page for o in q.options)})
        if len(pages) > 1:
            notes.append(f"spans pages {pages[0]}-{pages[-1]}")

        questions_out.append(
            {
                "id": question_uuid(q.week, q.qno),
                "source_week": q.week,
                "source_question_no": q.qno,
                "question_text": q.text,
                "source_pdf_page": q.page,
                "options": [
                    {
                        "id": option_uuid(q.week, q.qno, o.label),
                        "source_label": o.label,
                        "source_label_style": o.label_style,
                        "option_text": o.text,
                        "is_correct": i in bold_idx and len(bold_idx) == 1,
                        "source_was_bold": ratios[i] == 1.0,
                        "source_pdf_page": o.page,
                    }
                    for i, o in enumerate(q.options)
                ],
                "audit": {
                    "font_bold_check": font_check,
                    "render_stroke_check": render_check,
                    "trd_answer_key_check": trd_check,
                    "verification_status": status,
                    "issues": q_issues,
                    "notes": notes,
                },
            }
        )
        correct_label = q.options[bold_idx[0]].label if len(bold_idx) == 1 else ""
        audit_rows.append(
            {
                "week": q.week,
                "question_no": q.qno,
                "pdf_page": q.page,
                "question_id": question_uuid(q.week, q.qno),
                "correct_option_id": option_uuid(q.week, q.qno, correct_label) if correct_label else "",
                "correct_source_label": correct_label,
                "correct_option_text": correct_text,
                "font_bold_check": font_check,
                "render_stroke_check": render_check,
                "trd_answer_key_check": trd_check,
                "manual_visual_review": "agree" if visually_reviewed else "not_reviewed",
                "verification_status": status,
                "notes": "; ".join(q_issues + notes),
            }
        )

    # Structural / cross-question checks
    by_week: dict[int, int] = {}
    for q in questions_out:
        by_week[q["source_week"]] = by_week.get(q["source_week"], 0) + 1
    for w in range(1, EXPECTED_WEEKS + 1):
        if by_week.get(w, 0) != EXPECTED_PER_WEEK:
            issues.append(f"Week {w}: expected {EXPECTED_PER_WEEK} questions, found {by_week.get(w, 0)}")
    if len(questions_out) != EXPECTED_WEEKS * EXPECTED_PER_WEEK:
        issues.append(f"Expected 120 questions, found {len(questions_out)}")
    for (w, n) in trd_key:
        if (w, n) not in seen:
            issues.append(f"TRD lists W{w} Q{n} but it was not extracted")

    # Informational: identical question stems (not errors; source content is preserved).
    stems: dict[str, list[str]] = {}
    for q in questions_out:
        stems.setdefault(norm_for_match(q["question_text"]), []).append(f"W{q['source_week']} Q{q['source_question_no']}")
    repeated_stems = {k: v for k, v in stems.items() if len(v) > 1}

    unresolved = [q for q in questions_out if q["audit"]["verification_status"] != "verified"]
    args.out.mkdir(parents=True, exist_ok=True)

    seed = {
        "schema_version": 1,
        "source": {
            "file_name": args.pdf.name,
            "sha256": checksum,
            "page_count": doc.page_count,
        },
        "answer_rule": "Correct option = option text set in bold font in the source PDF, confirmed by rendered stroke weight, the TRD audit table, and a manual visual review.",
        "question_count": len(questions_out),
        "questions": questions_out,
    }
    (args.out / "questions.json").write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with (args.out / "answer_key_audit.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(audit_rows[0].keys()) if audit_rows else ["week"])
        writer.writeheader()
        writer.writerows(audit_rows)

    report = build_report(seed, by_week, issues, unresolved, repeated_stems, trd_key)
    (args.out / "import_validation_report.md").write_text(report, encoding="utf-8")

    print(f"Extracted {len(questions_out)} questions from {doc.page_count} pages")
    print(f"Per week: {dict(sorted(by_week.items()))}")
    print(f"Verified: {len(questions_out) - len(unresolved)}  Unresolved: {len(unresolved)}  Global issues: {len(issues)}")
    for msg in issues:
        print(f"  ISSUE: {msg}")
    for q in unresolved:
        print(f"  UNRESOLVED W{q['source_week']} Q{q['source_question_no']}: {q['audit']['issues']}")
    return 1 if (issues or unresolved) else 0


def build_report(seed, by_week, issues, unresolved, repeated_stems, trd_key) -> str:
    qs = seed["questions"]
    verified = len(qs) - len(unresolved)
    lines = [
        "# Import Validation Report",
        "",
        "Generated by `scripts/extract_questions.py` from the source PDF. Do not edit by hand; re-run the script.",
        "",
        "## Source",
        "",
        f"- File: `{seed['source']['file_name']}`",
        f"- SHA-256: `{seed['source']['sha256']}`",
        f"- Pages: {seed['source']['page_count']}",
        "",
        "## Method",
        "",
        "1. Text, font name, and bold flag are read per text span with PyMuPDF.",
        "2. Questions are segmented by week header, question numbering (`1.` inline or a bare number line), "
        "and option labels (`(a)` or `a.`); wrapped lines and page breaks are joined.",
        "3. **Font check:** exactly one option per question must be entirely set in a bold font; "
        "partially bold options are rejected.",
        f"4. **Rendered-page check:** each page is rasterised at {RENDER_ZOOM:.0f}x; the mean stroke width of the bold "
        f"option's glyphs must be at least {INK_MARGIN:.2f}x that of every other option in the question "
        "(bold = thicker, darker strokes).",
        f"5. **TRD cross-check:** the bold option text must match the answer-key audit table in `TRD.md` "
        f"({len(trd_key)} entries parsed).",
        "6. A question is `verified` only when all three checks pass and it has four non-blank, distinct options.",
        "",
        "## Summary",
        "",
        f"- Questions extracted: **{len(qs)}** (expected 120)",
        f"- Verified answers: **{verified}**",
        f"- Unresolved questions: **{len(unresolved)}**",
        f"- Global issues: **{len(issues)}**",
        "",
        "| Week | Questions |",
        "|---:|---:|",
    ]
    for w in sorted(by_week):
        lines.append(f"| {w} | {by_week[w]} |")
    lines += ["", "## Checks", ""]
    checks = {
        "Four options per question": all(len(q["options"]) == 4 for q in qs),
        "Exactly one correct option per question": all(sum(o["is_correct"] for o in q["options"]) == 1 for q in qs),
        "No blank question or option text": all(q["question_text"] and all(o["option_text"] for o in q["options"]) for q in qs),
        "Font bold check passed for all": all(q["audit"]["font_bold_check"] == "pass" for q in qs),
        "Rendered stroke-weight check passed for all": all(q["audit"]["render_stroke_check"] == "pass" for q in qs),
        "TRD answer-key match for all": all(q["audit"]["trd_answer_key_check"] == "pass" for q in qs),
    }
    for name, ok in checks.items():
        lines.append(f"- [{'x' if ok else ' '}] {name}")
    lines += ["", "## Issues", ""]
    if not issues and not unresolved:
        lines.append("None. All questions verified.")
    for msg in issues:
        lines.append(f"- {msg}")
    for q in unresolved:
        lines.append(f"- W{q['source_week']} Q{q['source_question_no']}: {'; '.join(q['audit']['issues'])}")
    lines += [
        "",
        "## Source observations (informational, wording preserved)",
        "",
        "These are not import errors. Source wording and marked answers are kept exactly as in the PDF.",
        "",
    ]
    if repeated_stems:
        for stem, where in sorted(repeated_stems.items(), key=lambda kv: kv[1]):
            lines.append(f"- Identical question stem appears in {', '.join(where)}: \"{stem}\"")
    multi_page = [q for q in qs if any("spans pages" in n for n in q["audit"]["notes"])]
    if multi_page:
        lines.append(
            "- Questions whose options continue onto the next PDF page: "
            + ", ".join(f"W{q['source_week']} Q{q['source_question_no']}" for q in multi_page)
        )
    dotted = [q for q in qs if q["options"] and q["options"][0]["source_label_style"] == "a."]
    if dotted:
        lines.append(
            "- Questions using `a.` option labels (all others use `(a)`): "
            + ", ".join(f"W{q['source_week']} Q{q['source_question_no']}" for q in dotted)
        )
    review = REPO_ROOT / "data" / "seed" / "manual_visual_review.md"
    if review.exists():
        lines += [
            "",
            "## Manual visual review",
            "",
            "See [`manual_visual_review.md`](manual_visual_review.md) for the page-by-page human comparison "
            "of rendered PDF pages against the extracted answer key.",
        ]
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
