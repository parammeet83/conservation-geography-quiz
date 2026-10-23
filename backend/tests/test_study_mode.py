"""Study Mode: immediate per-question feedback, locking, scoring, and answer confidentiality."""

import json
import threading
import uuid

import pytest
from sqlalchemy import select

from app.models import AttemptQuestion, Question
from app.services import quiz
from tests.conftest import SeededRandom, answer, auth, correct_option_ids

API = "/api/v1"


def start_study(client, mode: str = "weekly", week_no: int | None = 1) -> dict:
    body = {"mode": mode, "study_mode": True}
    if mode == "weekly":
        body["week_no"] = week_no
    r = client.post(f"{API}/attempts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def check(client, attempt: dict, aq_id: str, option_id: str | None, token: str | None = "own"):
    headers = auth(attempt["access_token"] if token == "own" else token) if token else {}
    return client.post(
        f"{API}/attempts/{attempt['id']}/questions/{aq_id}/study-answer",
        json={"selected_option_id": option_id},
        headers=headers,
    )


def wrong_option(q: dict, key: dict[str, str]) -> str:
    return next(o["id"] for o in q["options"] if o["id"] != key[q["attempt_question_id"]])


# ---- creation and confidentiality -------------------------------------------------------


@pytest.mark.parametrize("week", [1, 6, 12])
def test_study_attempt_uses_the_same_weekly_scope_and_shuffle(client, db, week):
    attempt = start_study(client, "weekly", week)
    assert attempt["study_mode"] is True and attempt["week_no"] == week
    assert attempt["total_questions"] == 10 and len(attempt["questions"]) == 10
    weeks = db.execute(
        select(Question.source_week)
        .join(AttemptQuestion, AttemptQuestion.question_id == Question.id)
        .where(AttemptQuestion.attempt_id == uuid.UUID(attempt["id"]))
    ).scalars()
    assert set(weeks) == {week}
    assert all([o["label"] for o in q["options"]] == ["A", "B", "C", "D"] for q in attempt["questions"])


def test_overall_study_attempt_has_all_120_questions(client):
    attempt = start_study(client, "overall")
    assert attempt["study_mode"] is True and attempt["total_questions"] == 120
    assert len({q["attempt_question_id"] for q in attempt["questions"]}) == 120


def test_quiz_mode_remains_the_default(client):
    r = client.post(f"{API}/attempts", json={"mode": "weekly", "week_no": 2})
    assert r.status_code == 201 and r.json()["study_mode"] is False


def test_no_answer_is_revealed_before_a_selection(client):
    attempt = start_study(client, "overall")
    payloads = [attempt, client.get(f"{API}/attempts/{attempt['id']}", headers=auth(attempt["access_token"])).json()]
    for payload in payloads:
        assert all(q["feedback"] is None for q in payload["questions"])
        text = json.dumps(payload).lower()
        assert "is_correct" not in text and "correct_option" not in text


# ---- immediate feedback ---------------------------------------------------------------------


def test_correct_selection_returns_immediate_positive_feedback(client, db):
    attempt = start_study(client)
    key = correct_option_ids(db, attempt)
    q = attempt["questions"][0]
    r = check(client, attempt, q["attempt_question_id"], key[q["attempt_question_id"]])
    assert r.status_code == 200
    body = r.json()
    assert body["is_correct"] is True
    assert body["correct_option_id"] == key[q["attempt_question_id"]]
    assert (body["answered_count"], body["correct_count"], body["total_questions"]) == (1, 1, 10)


def test_incorrect_selection_reveals_the_correct_option(client, db):
    attempt = start_study(client)
    key = correct_option_ids(db, attempt)
    q = attempt["questions"][1]
    chosen = wrong_option(q, key)
    body = check(client, attempt, q["attempt_question_id"], chosen).json()
    assert body["is_correct"] is False
    assert body["selected_option_id"] == chosen
    assert body["correct_option_id"] == key[q["attempt_question_id"]] != chosen
    assert (body["answered_count"], body["correct_count"]) == (1, 0)


def test_feedback_is_revealed_only_for_answered_questions_on_resume(client, db):
    attempt = start_study(client)
    key = correct_option_ids(db, attempt)
    q0, q1 = attempt["questions"][0], attempt["questions"][1]
    check(client, attempt, q0["attempt_question_id"], wrong_option(q0, key))
    resumed = client.get(f"{API}/attempts/{attempt['id']}", headers=auth(attempt["access_token"])).json()
    assert resumed["questions"][0]["feedback"] == {
        "is_correct": False,
        "correct_option_id": key[q0["attempt_question_id"]],
    }
    assert resumed["questions"][0]["selected_option_id"] == wrong_option(q0, key)
    assert all(q["feedback"] is None for q in resumed["questions"][1:])
    assert resumed["questions"][1]["attempt_question_id"] == q1["attempt_question_id"]


def test_shuffled_options_keep_the_correct_mapping_in_every_position(client, db, rng_holder):
    rng_holder["rng"] = SeededRandom(11)
    attempt = start_study(client, "overall")
    key = correct_option_ids(db, attempt)
    positions = set()
    for q in attempt["questions"]:
        ids = [o["id"] for o in q["options"]]
        positions.add(ids.index(key[q["attempt_question_id"]]))
        body = check(client, attempt, q["attempt_question_id"], key[q["attempt_question_id"]]).json()
        assert body["is_correct"] is True and body["correct_option_id"] == key[q["attempt_question_id"]]
    assert positions == {0, 1, 2, 3}


# ---- locking ---------------------------------------------------------------------------------


def test_question_locks_after_first_answer(client, db):
    attempt = start_study(client)
    key = correct_option_ids(db, attempt)
    q = attempt["questions"][0]
    first = wrong_option(q, key)
    assert check(client, attempt, q["attempt_question_id"], first).status_code == 200

    # A different guess is rejected and the original answer stands.
    r = check(client, attempt, q["attempt_question_id"], key[q["attempt_question_id"]])
    assert r.status_code == 409 and r.json()["error"]["code"] == "question_locked"
    # Re-sending the same choice (e.g. a network retry) returns the same result.
    again = check(client, attempt, q["attempt_question_id"], first).json()
    assert again["is_correct"] is False and again["answered_count"] == 1 and again["correct_count"] == 0

    # The Quiz Mode save endpoint cannot change or clear a Study Mode answer.
    for option in (key[q["attempt_question_id"]], None):
        r = answer(client, attempt, q["attempt_question_id"], option)
        assert r.status_code == 409 and r.json()["error"]["code"] == "study_mode_attempt"
    resumed = client.get(f"{API}/attempts/{attempt['id']}", headers=auth(attempt["access_token"])).json()
    assert resumed["questions"][0]["selected_option_id"] == first


def test_concurrent_different_guesses_lock_in_exactly_one(client, db, session_factory):
    attempt = start_study(client)
    q = attempt["questions"][0]
    options = [o["id"] for o in q["options"]]
    outcomes = []
    barrier = threading.Barrier(4)

    def worker(option_id):
        with session_factory() as s:
            barrier.wait()
            try:
                quiz.check_study_answer(
                    s,
                    uuid.UUID(attempt["id"]),
                    attempt["access_token"],
                    uuid.UUID(q["attempt_question_id"]),
                    uuid.UUID(option_id),
                )
                outcomes.append("ok")
            except quiz.ApiError as exc:
                outcomes.append(exc.code)

    threads = [threading.Thread(target=worker, args=(o,)) for o in options]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["ok", "question_locked", "question_locked", "question_locked"]


# ---- scoring and completion -------------------------------------------------------------------


def test_study_session_scoring_matches_feedback(client, db):
    attempt = start_study(client, "weekly", 9)
    key = correct_option_ids(db, attempt)
    qs = attempt["questions"]
    for q in qs[:6]:
        check(client, attempt, q["attempt_question_id"], key[q["attempt_question_id"]])
    for q in qs[6:9]:
        last = check(client, attempt, q["attempt_question_id"], wrong_option(q, key)).json()
    assert (last["answered_count"], last["correct_count"]) == (9, 6)
    # qs[9] left unanswered; finishing the session uses the existing submit endpoint.
    result = client.post(f"{API}/attempts/{attempt['id']}/submit", headers=auth(attempt["access_token"])).json()
    assert result["study_mode"] is True
    assert (result["correct_count"], result["incorrect_count"], result["unanswered_count"]) == (6, 3, 1)
    assert result["score_correct"] == 6 and result["score_percent"] == 60.0

    r = check(client, attempt, qs[9]["attempt_question_id"], key[qs[9]["attempt_question_id"]])
    assert r.status_code == 409 and r.json()["error"]["code"] == "attempt_not_in_progress"


# ---- validation and authorisation ----------------------------------------------------------------


def test_quiz_mode_attempts_cannot_use_the_study_endpoint(client, db):
    r = client.post(f"{API}/attempts", json={"mode": "weekly", "week_no": 3})
    attempt = r.json()
    q = attempt["questions"][0]
    r = check(client, attempt, q["attempt_question_id"], q["options"][0]["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_study_mode"
    assert "correct_option_id" not in r.text
    # Nothing was recorded.
    resumed = client.get(f"{API}/attempts/{attempt['id']}", headers=auth(attempt["access_token"])).json()
    assert resumed["answered_count"] == 0


def test_study_endpoint_requires_the_attempt_token(client):
    attempt = start_study(client)
    other = start_study(client)
    q = attempt["questions"][0]
    r = check(client, attempt, q["attempt_question_id"], q["options"][0]["id"], token=None)
    assert r.status_code == 401 and r.json()["error"]["code"] == "missing_token"
    r = check(client, attempt, q["attempt_question_id"], q["options"][0]["id"], token=other["access_token"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "invalid_token"
    assert "correct_option_id" not in r.text


def test_study_endpoint_validates_question_and_option(client):
    attempt = start_study(client)
    other = start_study(client)
    q0, q1 = attempt["questions"][0], attempt["questions"][1]
    r = check(client, attempt, q0["attempt_question_id"], q1["options"][0]["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "option_not_in_question"
    r = check(client, attempt, q0["attempt_question_id"], str(uuid.uuid4()))
    assert r.status_code == 422
    r = check(client, attempt, other["questions"][0]["attempt_question_id"], other["questions"][0]["options"][0]["id"])
    assert r.status_code == 404 and r.json()["error"]["code"] == "question_not_in_attempt"
    r = check(client, attempt, q0["attempt_question_id"], None)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = client.post(
        f"{API}/attempts/{attempt['id']}/questions/{q0['attempt_question_id']}/study-answer",
        json={"selected_option_id": q0["options"][0]["id"], "is_correct": True},
        headers=auth(attempt["access_token"]),
    )
    assert r.status_code == 422
    for body in ({"mode": "weekly", "week_no": 1, "study_mode": "maybe"},):
        assert client.post(f"{API}/attempts", json=body).status_code == 422
