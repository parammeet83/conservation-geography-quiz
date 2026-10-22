"""Question-bank file validation (no database required)."""

import copy
import re

import pytest

from app.config import REPO_ROOT, get_settings
from app.seed import load_audit_rows, load_seed_document, validate_seed_document


@pytest.fixture(scope="module")
def seed_doc() -> dict:
    return load_seed_document(get_settings().seed_file)


@pytest.fixture(scope="module")
def audit_rows() -> list[dict]:
    return load_audit_rows(get_settings().audit_file)


def test_committed_seed_is_valid(seed_doc, audit_rows):
    result = validate_seed_document(seed_doc, audit_rows)
    assert result.errors == []
    assert result.question_count == 120
    assert result.week_counts == {w: 10 for w in range(1, 13)}


def test_every_question_has_four_options_and_one_correct(seed_doc):
    for q in seed_doc["questions"]:
        assert len(q["options"]) == 4
        assert sum(o["is_correct"] for o in q["options"]) == 1
        assert all(o["option_text"].strip() for o in q["options"])
        assert q["question_text"].strip()


def test_source_identities_unique_and_complete(seed_doc):
    idents = {(q["source_week"], q["source_question_no"]) for q in seed_doc["questions"]}
    assert idents == {(w, n) for w in range(1, 13) for n in range(1, 11)}
    assert len({q["id"] for q in seed_doc["questions"]}) == 120
    assert len({o["id"] for q in seed_doc["questions"] for o in q["options"]}) == 480


def test_audit_covers_every_question_with_verified_status(seed_doc, audit_rows):
    assert len(audit_rows) == 120
    assert {r["verification_status"] for r in audit_rows} == {"verified"}
    for col in ("font_bold_check", "render_stroke_check", "trd_answer_key_check"):
        assert {r[col] for r in audit_rows} == {"pass"}, col


def _trd_key() -> dict[tuple[int, int], str]:
    key, week = {}, None
    for raw in (REPO_ROOT / "TRD.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^###\s+Week\s+(\d+)\s*$", raw.strip())
        if m:
            week = int(m.group(1))
            continue
        m = re.match(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*$", raw.strip())
        if m and week:
            key[(week, int(m.group(1)))] = m.group(2)
    return key


def _norm(s: str) -> str:
    return " ".join(s.replace("’", "'").split()).casefold()


@pytest.mark.skipif(not (REPO_ROOT / "TRD.md").exists(), reason="TRD.md not present")
def test_seed_answers_match_trd_audit_table(seed_doc):
    key = _trd_key()
    assert len(key) == 120
    for q in seed_doc["questions"]:
        correct = next(o for o in q["options"] if o["is_correct"])
        assert _norm(correct["option_text"]) == _norm(key[(q["source_week"], q["source_question_no"])]), (
            q["source_week"],
            q["source_question_no"],
        )


# ---- the validator rejects broken data ----------------------------------------------


def _mutated(seed_doc, fn) -> dict:
    doc = copy.deepcopy(seed_doc)
    fn(doc)
    return doc


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda d: d["questions"][0]["options"].pop(), "expected 4 options"),
        (
            lambda d: next(o for o in d["questions"][0]["options"] if not o["is_correct"]).update(
                is_correct=True, source_was_bold=True
            ),
            "exactly 1 correct",
        ),
        (lambda d: [o.update(is_correct=False) for o in d["questions"][0]["options"]], "exactly 1 correct"),
        (lambda d: d["questions"][0].update(question_text="   "), "blank question text"),
        (lambda d: d["questions"][0]["options"][0].update(option_text=""), "blank option text"),
        (lambda d: d["questions"][1].update(source_question_no=1), "duplicate (week, question_number)"),
        (lambda d: d["questions"].pop(), "expected 120 questions"),
        (lambda d: d["questions"][5]["audit"].update(verification_status="unresolved"), "not 'verified'"),
        (lambda d: d["questions"][5]["audit"].update(issues=["ambiguous bold"]), "unresolved import issues"),
        (
            lambda d: d["questions"][2]["options"][3].update(
                option_text=d["questions"][2]["options"][2]["option_text"]
            ),
            "duplicate option text",
        ),
    ],
)
def test_validator_rejects(seed_doc, audit_rows, mutation, expected):
    result = validate_seed_document(_mutated(seed_doc, mutation), audit_rows)
    assert not result.ok
    assert any(expected in e for e in result.errors), result.errors


def test_validator_rejects_missing_audit_row(seed_doc, audit_rows):
    result = validate_seed_document(seed_doc, audit_rows[1:])
    assert any("audit: no row" in e for e in result.errors)


def test_validator_rejects_audit_answer_mismatch(seed_doc, audit_rows):
    rows = copy.deepcopy(audit_rows)
    rows[0]["correct_option_id"] = (
        seed_doc["questions"][0]["options"][0]["id"]
        if not seed_doc["questions"][0]["options"][0]["is_correct"]
        else seed_doc["questions"][0]["options"][1]["id"]
    )
    result = validate_seed_document(seed_doc, rows)
    assert any("correct_option_id does not match" in e for e in result.errors)
