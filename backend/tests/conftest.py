"""Shared fixtures. Database tests run against TEST_DATABASE_URL (never the app database)."""

import random
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import get_rng
from app.config import get_settings
from app.db import get_session, make_engine
from app.main import app
from app.seed import seed_database

BACKEND_DIR = Path(__file__).resolve().parents[1]


class SeededRandom:
    """Deterministic random source for reproducible shuffles in tests."""

    def __init__(self, seed: int):
        self._r = random.Random(seed)
        self.calls = 0

    def randbelow(self, n: int) -> int:
        self.calls += 1
        return self._r.randrange(n)


def _test_url() -> str:
    url = get_settings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; database tests skipped")
    if url == get_settings().database_url:
        pytest.exit("TEST_DATABASE_URL must differ from DATABASE_URL: tests drop and recreate tables.")
    return url


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = _test_url()
    eng = make_engine(url)
    # Start from an empty schema, then build it through the real migrations.
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")
    settings = get_settings()
    SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    with SessionLocal() as s:
        seed_database(s, settings.seed_file, settings.audit_file)
        s.commit()
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db(session_factory) -> Iterator[Session]:
    with session_factory() as s:
        yield s


@pytest.fixture(autouse=True)
def _clean_attempts(request) -> Iterator[None]:
    yield
    if "engine" in request.fixturenames:
        eng = request.getfixturevalue("engine")
        with eng.begin() as conn:
            conn.execute(text("TRUNCATE quiz_attempts CASCADE"))


@pytest.fixture
def rng_holder() -> dict:
    return {"rng": None}


@pytest.fixture
def client(session_factory, rng_holder) -> Iterator[TestClient]:
    def _session() -> Iterator[Session]:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    def _rng():
        return rng_holder["rng"] or get_rng()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_rng] = _rng
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---- helpers -------------------------------------------------------------------


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def start(client: TestClient, mode: str = "weekly", week_no: int | None = 1) -> dict:
    body = {"mode": mode} if mode == "overall" else {"mode": mode, "week_no": week_no}
    r = client.post("/api/v1/attempts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def answer(client: TestClient, attempt: dict, aq_id: str, option_id: str | None):
    return client.put(
        f"/api/v1/attempts/{attempt['id']}/questions/{aq_id}/answer",
        json={"selected_option_id": option_id},
        headers=auth(attempt["access_token"]),
    )


def correct_option_ids(db: Session, attempt: dict) -> dict[str, str]:
    """Map attempt_question_id -> correct option id, read directly from the database."""
    rows = db.execute(
        text(
            "SELECT aq.id, o.id FROM attempt_questions aq "
            "JOIN options o ON o.question_id = aq.question_id AND o.is_correct "
            "WHERE aq.attempt_id = :aid"
        ),
        {"aid": uuid.UUID(attempt["id"])},
    ).all()
    return {str(a): str(o) for a, o in rows}
