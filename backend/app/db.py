"""Database engine and session management."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def make_engine(url: str) -> Engine:
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)

    # Return every timestamp in UTC. Set after connecting rather than as a startup
    # parameter, which connection poolers such as Neon's PgBouncer endpoint reject.
    @event.listens_for(engine, "connect")
    def _utc(dbapi_conn, _record) -> None:
        with dbapi_conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC'")
        dbapi_conn.commit()

    return engine


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, rolled back on error."""
    session = get_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
