"""API integration tests: catalogue, attempts, randomisation, answers, grading, security."""

import json
import logging
import threading
import uuid

import pytest
from sqlalchemy import select, text, update

from app.models import Question
from app.services import quiz
from app.shuffle import fisher_yates
from tests.conftest import SeededRandom, answer, auth, correct_option_ids, start

API = "/api/v1"
FORBIDDEN_KEYS = {
    "is_correct",
    "correct_option_id",
    "correct_option_text",
    "correct_label",
    "source_was_bold",
    "source_label",
    "score_correct",
    "score_percent",
    "review",
}


def _keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | set().union(*(_keys(v) for v in obj.values())) if obj else set()
    if isinstance(obj, list):
        return set().union(*(_keys(v) for v in obj)) if obj else set()
    return set()


def _question_weeks(db, attempt) -> list[int]:
    return list(
        db.execute(
            text(
                "SELECT q.source_week FROM attempt_questions aq JOIN questions q ON q.id = aq.question_id "
                "WHERE aq.attempt_id = :a ORDER BY aq.display_order"
            ),
            {"a": uuid.UUID(attempt["id"])},
        ).scalars()
    )


def _assert_valid_structure(db, attempt, expected_total):
    assert attempt["total_questions"] == expected_total
    assert len(attempt["questions"]) == expected_total
    assert [q["position"] for q in attempt["questions"]] == list(range(1, expected_total + 1))
    rows = db.execute(
        text(
            "SELECT aq.id, o.id FROM attempt_questions aq JOIN options o ON o.question_id = aq.question_id "
            "WHERE aq.attempt_id = :a"
        ),
        {"a": uuid.UUID(attempt["id"])},
    ).all()
    canonical: dict[str, set[str]] = {}
    for aq, o in rows:
        canonical.setdefault(str(aq), set()).add(str(o))
    for q in attempt["questions"]:
        assert [o["label"] for o in q["options"]] == ["A", "B", "C", "D"]
        ids = [o["id"] for o in q["options"]]
        assert len(set(ids)) == 4
        assert set(ids) == canonical[q["attempt_question_id"]]
        assert q["selected_option_id"] is None


# ---- health and catalogue ------------------------------------------------------------------


def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_catalogue_lists_twelve_weeks_and_overall_from_database(client):
    data = client.get(f"{API}/quizzes").json()
    assert [w["week_no"] for w in data["weeks"]] == list(range(1, 13))
    assert all(w["question_count"] == 10 and w["available"] for w in data["weeks"])
    assert [w["title"] for w in data["weeks"]] == [f"Week {n}" for n in range(1, 13)]
    assert data["overall"] == {"title": "Overall Quiz", "question_count": 120, "available": True}


def test_catalogue_and_creation_reflect_an_invalid_bank(client, db):
    qid = db.scalars(select(Question.id).where(Question.source_week == 4).limit(1)).first()
    db.execute(update(Question).where(Question.id == qid).values(is_active=False))
    db.commit()
    try:
        data = client.get(f"{API}/quizzes").json()
        assert data["weeks"][3] == {"week_no": 4, "title": "Week 4", "question_count": 9, "available": False}
        assert data["overall"]["available"] is False
        r = client.post(f"{API}/attempts", json={"mode": "weekly", "week_no": 4})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "question_bank_invalid"
        assert client.post(f"{API}/attempts", json={"mode": "overall"}).status_code == 503
    finally:
        db.execute(update(Question).where(Question.id == qid).values(is_active=True))
        db.commit()


# ---- attempt creation and coverage -------------------------------------------------------------


@pytest.mark.parametrize("week", range(1, 13))
def test_weekly_attempt_contains_exactly_that_weeks_ten_questions(client, db, week):
    attempt = start(client, "weekly", week)
    assert attempt["title"] == f"Week {week}"
    assert attempt["mode"] == "weekly" and attempt["week_no"] == week
    _assert_valid_structure(db, attempt, 10)
    weeks = _question_weeks(db, attempt)
    assert weeks == [week] * 10
    qids = (
        db.execute(
            text("SELECT question_id FROM attempt_questions WHERE attempt_id = :a"), {"a": uuid.UUID(attempt["id"])}
        )
        .scalars()
        .all()
    )
    expected = db.scalars(select(Question.id).where(Question.source_week == week, Question.is_active)).all()
    assert set(qids) == set(expected)


def test_overall_attempt_contains_all_120_questions_once(client, db):
    attempt = start(client, "overall")
    assert attempt["title"] == "Overall Quiz" and attempt["week_no"] is None
    _assert_valid_structure(db, attempt, 120)
    qids = (
        db.execute(
            text("SELECT question_id FROM attempt_questions WHERE attempt_id = :a"), {"a": uuid.UUID(attempt["id"])}
        )
        .scalars()
        .all()
    )
    assert len(qids) == 120 and len(set(qids)) == 120
    assert set(qids) == set(db.scalars(select(Question.id).where(Question.is_active)).all())
    assert sorted(_question_weeks(db, attempt)) == sorted([w for w in range(1, 13) for _ in range(10)])


@pytest.mark.parametrize(
    "body",
    [
        {"mode": "weekly"},
        {"mode": "weekly", "week_no": 0},
        {"mode": "weekly", "week_no": 13},
        {"mode": "overall", "week_no": 2},
        {"mode": "monthly"},
        {"mode": "weekly", "week_no": 1, "score": 10},
    ],
)
def test_attempt_creation_validates_input(client, body):
    r = client.post(f"{API}/attempts", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


# ---- randomisation ---------------------------------------------------------------------------


def test_shuffle_uses_injected_rng_and_persists_exact_permutation(client, db, rng_holder):
    rng_holder["rng"] = SeededRandom(42)
    attempt = start(client, "weekly", 2)
    # 1 question shuffle + 10 option shuffles = 11 Fisher-Yates runs: 9 + 10 * 3 random draws.
    assert rng_holder["rng"].calls == 9 + 10 * 3

    # Recompute the expected permutation independently from the canonical, ordered bank.
    questions = db.scalars(
        select(Question).where(Question.source_week == 2).order_by(Question.source_question_no)
    ).all()
    replay = SeededRandom(42)
    expected_q = fisher_yates(questions, replay)
    assert [q["question_text"] for q in attempt["questions"]] == [q.question_text for q in expected_q]
    for shown, q in zip(attempt["questions"], expected_q, strict=True):
        expected_opts = fisher_yates(sorted(q.options, key=lambda o: o.source_label), replay)
        assert [o["id"] for o in shown["options"]] == [str(o.id) for o in expected_opts]


def test_new_attempts_get_fresh_permutations(client, rng_holder):
    rng_holder["rng"] = SeededRandom(1)
    a = start(client, "overall")
    rng_holder["rng"] = SeededRandom(2)
    b = start(client, "overall")
    order_a = [q["question_text"] for q in a["questions"]]
    order_b = [q["question_text"] for q in b["questions"]]
    assert sorted(order_a) == sorted(order_b)
    assert order_a != order_b  # deterministic seeds, so this is not flaky
    assert a["id"] != b["id"] and a["access_token"] != b["access_token"]


def test_option_orders_vary_independently_per_question(client, rng_holder):
    rng_holder["rng"] = SeededRandom(9)
    attempt = start(client, "overall")
    by_text: dict[str, list[str]] = {}
    for q in attempt["questions"]:
        by_text[q["question_text"]] = [o["text"] for o in q["options"]]
    # With independent shuffles, correct/first-source options land in all four positions across questions.
    first_positions = {tuple(opts).index(sorted(opts)[0]) for opts in by_text.values() if len(set(opts)) == 4}
    assert first_positions == {0, 1, 2, 3}


def test_resume_returns_the_same_stored_order_and_answers(client):
    attempt = start(client, "overall")
    q = attempt["questions"][57]
    assert answer(client, attempt, q["attempt_question_id"], q["options"][2]["id"]).status_code == 200
    h = auth(attempt["access_token"])
    first = client.get(f"{API}/attempts/{attempt['id']}", headers=h).json()
    second = client.get(f"{API}/attempts/{attempt['id']}", headers=h).json()
    assert first == second
    strip = lambda qs: [(x["attempt_question_id"], [o["id"] for o in x["options"]]) for x in qs]  # noqa: E731
    assert strip(first["questions"]) == strip(attempt["questions"])
    assert first["questions"][57]["selected_option_id"] == q["options"][2]["id"]
    assert first["answered_count"] == 1
    assert "access_token" not in first


# ---- answer key confidentiality -----------------------------------------------------------------


def test_active_attempt_payloads_never_expose_correctness(client):
    attempt = start(client, "overall")
    h = auth(attempt["access_token"])
    q = attempt["questions"][0]
    saved = answer(client, attempt, q["attempt_question_id"], q["options"][0]["id"]).json()
    resumed = client.get(f"{API}/attempts/{attempt['id']}", headers=h).json()
    for payload in (attempt, saved, resumed):
        assert not (_keys(payload) & FORBIDDEN_KEYS)
        assert "correct" not in json.dumps(payload).lower().replace("incorrect", "")
    allowed_question_keys = {
        "attempt_question_id",
        "position",
        "question_text",
        "options",
        "selected_option_id",
        "feedback",
    }
    assert all(set(x) == allowed_question_keys for x in resumed["questions"])
    # Quiz Mode never carries Study Mode feedback, even for answered questions.
    assert resumed["study_mode"] is False
    assert all(x["feedback"] is None for x in resumed["questions"])
    assert all(set(o) == {"id", "label", "text"} for x in resumed["questions"] for o in x["options"])


def test_result_is_unavailable_before_submission(client):
    attempt = start(client)
    r = client.get(f"{API}/attempts/{attempt['id']}/result", headers=auth(attempt["access_token"]))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "attempt_not_submitted"
    assert "correct_option" not in r.text


# ---- answering ----------------------------------------------------------------------------------


def test_save_change_and_clear_answer(client):
    attempt = start(client)
    q = attempt["questions"][3]
    r = answer(client, attempt, q["attempt_question_id"], q["options"][0]["id"])
    assert r.status_code == 200
    assert r.json()["answered_count"] == 1 and r.json()["selected_option_id"] == q["options"][0]["id"]
    r = answer(client, attempt, q["attempt_question_id"], q["options"][3]["id"])
    assert r.json()["selected_option_id"] == q["options"][3]["id"] and r.json()["answered_count"] == 1
    r = answer(client, attempt, q["attempt_question_id"], None)
    assert r.json()["selected_option_id"] is None and r.json()["answered_count"] == 0
    assert r.json()["answered_at"] is None


def test_rejects_unknown_option(client):
    attempt = start(client)
    q = attempt["questions"][0]
    r = answer(client, attempt, q["attempt_question_id"], str(uuid.uuid4()))
    assert r.status_code == 422 and r.json()["error"]["code"] == "option_not_in_question"


def test_rejects_option_from_another_question_in_same_attempt(client):
    attempt = start(client)
    q0, q1 = attempt["questions"][0], attempt["questions"][1]
    r = answer(client, attempt, q0["attempt_question_id"], q1["options"][0]["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "option_not_in_question"


def test_rejects_option_from_a_question_outside_the_attempt(client):
    week1 = start(client, "weekly", 1)
    week2 = start(client, "weekly", 2)
    r = answer(client, week1, week1["questions"][0]["attempt_question_id"], week2["questions"][0]["options"][0]["id"])
    assert r.status_code == 422


def test_rejects_question_from_another_attempt(client):
    a = start(client)
    b = start(client)
    r = answer(client, a, b["questions"][0]["attempt_question_id"], b["questions"][0]["options"][0]["id"])
    assert r.status_code == 404 and r.json()["error"]["code"] == "question_not_in_attempt"


def test_answer_body_is_validated(client):
    attempt = start(client)
    q = attempt["questions"][0]
    url = f"{API}/attempts/{attempt['id']}/questions/{q['attempt_question_id']}/answer"
    h = auth(attempt["access_token"])
    assert client.put(url, json={"selected_option_id": "not-a-uuid"}, headers=h).status_code == 422
    assert client.put(url, json={}, headers=h).status_code == 422
    assert client.put(url, json={"selected_option_id": None, "is_correct": True}, headers=h).status_code == 422


# ---- grading --------------------------------------------------------------------------------------


def _submit(client, attempt, **kw):
    return client.post(f"{API}/attempts/{attempt['id']}/submit", headers=auth(attempt["access_token"]), **kw)


def test_correct_answers_are_graded_correct_in_every_display_position(client, db, rng_holder):
    rng_holder["rng"] = SeededRandom(5)
    attempt = start(client, "overall")
    key = correct_option_ids(db, attempt)
    positions = set()
    for q in attempt["questions"]:
        ids = [o["id"] for o in q["options"]]
        positions.add(ids.index(key[q["attempt_question_id"]]))
        assert answer(client, attempt, q["attempt_question_id"], key[q["attempt_question_id"]]).status_code == 200
    assert positions == {0, 1, 2, 3}  # correct answer appears at A, B, C and D

    result = _submit(client, attempt).json()
    assert result["score_correct"] == 120 and result["score_percent"] == 100.0
    assert result["correct_count"] == 120 and result["incorrect_count"] == 0 and result["unanswered_count"] == 0
    for item in result["review"]:
        assert item["status"] == "correct"
        assert item["selected_option_id"] == item["correct_option_id"]
        assert item["selected_label"] == item["correct_label"]
    seen_labels = {item["correct_label"] for item in result["review"]}
    assert seen_labels == {"A", "B", "C", "D"}


def test_mixed_weekly_scoring_with_incorrect_unanswered_and_changed_answers(client, db):
    attempt = start(client, "weekly", 7)
    key = correct_option_ids(db, attempt)
    qs = attempt["questions"]
    wrong = lambda q: next(o["id"] for o in q["options"] if o["id"] != key[q["attempt_question_id"]])  # noqa: E731

    for q in qs[:3]:  # 3 correct
        answer(client, attempt, q["attempt_question_id"], key[q["attempt_question_id"]])
    for q in qs[3:7]:  # 4 incorrect
        answer(client, attempt, q["attempt_question_id"], wrong(q))
    # changed from wrong to right -> correct (4 correct total)
    answer(client, attempt, qs[7]["attempt_question_id"], wrong(qs[7]))
    answer(client, attempt, qs[7]["attempt_question_id"], key[qs[7]["attempt_question_id"]])
    # changed from right to cleared -> unanswered
    answer(client, attempt, qs[8]["attempt_question_id"], key[qs[8]["attempt_question_id"]])
    answer(client, attempt, qs[8]["attempt_question_id"], None)
    # qs[9] never answered

    result = _submit(client, attempt).json()
    assert result["total_questions"] == 10
    assert (result["correct_count"], result["incorrect_count"], result["unanswered_count"]) == (4, 4, 2)
    assert result["score_correct"] == 4 and result["score_percent"] == 40.0
    review = {r["attempt_question_id"]: r for r in result["review"]}
    assert review[qs[9]["attempt_question_id"]]["status"] == "unanswered"
    assert review[qs[9]["attempt_question_id"]]["selected_option_text"] is None
    assert review[qs[8]["attempt_question_id"]]["status"] == "unanswered"
    assert review[qs[4]["attempt_question_id"]]["status"] == "incorrect"
    assert review[qs[7]["attempt_question_id"]]["status"] == "correct"
    assert [r["position"] for r in result["review"]] == list(range(1, 11))


def test_overall_percentage_rounding(client, db):
    attempt = start(client, "overall")
    key = correct_option_ids(db, attempt)
    q = attempt["questions"][119]
    answer(client, attempt, q["attempt_question_id"], key[q["attempt_question_id"]])
    result = _submit(client, attempt).json()
    assert result["score_correct"] == 1 and result["score_percent"] == 0.83
    assert result["unanswered_count"] == 119


def test_empty_submission_scores_zero(client):
    attempt = start(client, "weekly", 12)
    result = _submit(client, attempt).json()
    assert result["score_correct"] == 0 and result["score_percent"] == 0.0 and result["unanswered_count"] == 10


def test_submission_is_idempotent_and_attempt_becomes_immutable(client, db):
    attempt = start(client, "weekly", 3)
    key = correct_option_ids(db, attempt)
    q = attempt["questions"][0]
    answer(client, attempt, q["attempt_question_id"], key[q["attempt_question_id"]])
    first = _submit(client, attempt).json()
    second = _submit(client, attempt).json()
    assert first == second
    fetched = client.get(f"{API}/attempts/{attempt['id']}/result", headers=auth(attempt["access_token"])).json()
    assert fetched == first

    r = answer(client, attempt, q["attempt_question_id"], None)
    assert r.status_code == 409 and r.json()["error"]["code"] == "attempt_not_in_progress"
    status = client.get(f"{API}/attempts/{attempt['id']}", headers=auth(attempt["access_token"])).json()
    assert status["status"] == "submitted"
    assert status["questions"][0]["selected_option_id"] == key[q["attempt_question_id"]]


def test_submit_rejects_client_supplied_score(client):
    attempt = start(client)
    r = _submit(client, attempt, json={"score_correct": 10, "score_percent": 100})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unexpected_fields"
    assert (
        client.get(f"{API}/attempts/{attempt['id']}", headers=auth(attempt["access_token"])).json()["status"]
        == "in_progress"
    )


def test_concurrent_duplicate_submissions_grade_once(client, db, session_factory):
    attempt = start(client, "weekly", 5)
    key = correct_option_ids(db, attempt)
    for q in attempt["questions"][:6]:
        answer(client, attempt, q["attempt_question_id"], key[q["attempt_question_id"]])

    results, errors = [], []
    barrier = threading.Barrier(5)

    def worker():
        try:
            with session_factory() as s:
                barrier.wait()
                results.append(quiz.submit_attempt(s, uuid.UUID(attempt["id"]), attempt["access_token"]))
        except Exception as exc:  # pragma: no cover - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len({(r.score_correct, r.submitted_at) for r in results}) == 1
    assert results[0].score_correct == 6 and results[0].score_percent == 60.0


def test_save_racing_submit_never_changes_a_graded_attempt(client, db, session_factory):
    attempt = start(client, "weekly", 6)
    key = correct_option_ids(db, attempt)
    q = attempt["questions"][0]
    outcomes = []
    barrier = threading.Barrier(2)

    def do_submit():
        with session_factory() as s:
            barrier.wait()
            outcomes.append(("submit", quiz.submit_attempt(s, uuid.UUID(attempt["id"]), attempt["access_token"])))

    def do_save():
        with session_factory() as s:
            barrier.wait()
            try:
                quiz.save_answer(
                    s,
                    uuid.UUID(attempt["id"]),
                    attempt["access_token"],
                    uuid.UUID(q["attempt_question_id"]),
                    uuid.UUID(key[q["attempt_question_id"]]),
                )
                outcomes.append(("save", "ok"))
            except quiz.ApiError as exc:
                outcomes.append(("save", exc.code))

    threads = [threading.Thread(target=do_submit), threading.Thread(target=do_save)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = client.get(f"{API}/attempts/{attempt['id']}/result", headers=auth(attempt["access_token"])).json()
    save_outcome = dict(outcomes)["save"]
    # Either the save landed before grading (and is counted) or it was rejected after grading.
    assert (save_outcome, final["score_correct"]) in {("ok", 1), ("attempt_not_in_progress", 0)}


# ---- access control ---------------------------------------------------------------------------------


def _routes(attempt):
    aid, q = attempt["id"], attempt["questions"][0]
    return [
        ("get", f"{API}/attempts/{aid}", None),
        (
            "put",
            f"{API}/attempts/{aid}/questions/{q['attempt_question_id']}/answer",
            {"selected_option_id": q["options"][0]["id"]},
        ),
        ("post", f"{API}/attempts/{aid}/submit", None),
        ("get", f"{API}/attempts/{aid}/result", None),
    ]


def test_missing_token_is_rejected_on_every_attempt_route(client):
    attempt = start(client)
    for method, url, body in _routes(attempt):
        r = client.request(method, url, json=body)
        assert r.status_code == 401, (method, url)
        assert r.json()["error"]["code"] == "missing_token"
        assert r.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("header", ["Bearer wrong-token", "Basic abc", "Bearer ", "token-without-scheme"])
def test_invalid_token_is_rejected(client, header):
    attempt = start(client)
    for method, url, body in _routes(attempt):
        r = client.request(method, url, json=body, headers={"Authorization": header})
        assert r.status_code in (401, 403), (method, url, header)


def test_token_of_another_attempt_cannot_read_or_modify(client):
    victim = start(client)
    other = start(client)
    for method, url, body in _routes(victim):
        r = client.request(method, url, json=body, headers=auth(other["access_token"]))
        assert r.status_code == 403, (method, url)
        assert r.json()["error"]["code"] == "invalid_token"
    # The victim's attempt is untouched.
    assert (
        client.get(f"{API}/attempts/{victim['id']}", headers=auth(victim["access_token"])).json()["answered_count"] == 0
    )


def test_unknown_and_malformed_attempt_ids(client):
    attempt = start(client)
    h = auth(attempt["access_token"])
    r = client.get(f"{API}/attempts/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404 and r.json()["error"]["code"] == "attempt_not_found"
    assert client.get(f"{API}/attempts/12345", headers=h).status_code == 422


def test_tokens_are_never_logged(client, caplog):
    caplog.set_level(logging.DEBUG)
    attempt = start(client)
    token = attempt["access_token"]
    q = attempt["questions"][0]
    answer(client, attempt, q["attempt_question_id"], q["options"][0]["id"])
    _submit(client, attempt)
    client.get(f"{API}/attempts/{attempt['id']}", headers={"Authorization": "Bearer wrong"})
    assert token not in caplog.text
    assert "Bearer" not in caplog.text


def test_cors_preflight_allows_configured_origin_only(client):
    ok = client.options(
        f"{API}/attempts",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options(
        f"{API}/attempts",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers
