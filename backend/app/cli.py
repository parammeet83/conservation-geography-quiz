"""Command-line tools: ``python -m app.cli {validate,seed,check-db}``.

validate   Validate data/seed/questions.json and answer_key_audit.csv (no database needed).
seed       Validate, then idempotently load the question bank into the database.
check-db   Run the question-bank integrity checks against the database.
release    Apply Alembic migrations, then seed, then check-db (used by the deployment job).

Each command exits non-zero on any failure.
"""

import argparse
import sys

from app.config import get_settings
from app.db import get_sessionmaker
from app.seed import (
    SeedValidationError,
    load_audit_rows,
    load_seed_document,
    seed_database,
    validate_database,
    validate_seed_document,
)


def _print_errors(errors: list[str]) -> None:
    for e in errors:
        print(f"  - {e}")


def cmd_validate() -> int:
    s = get_settings()
    doc = load_seed_document(s.seed_file)
    result = validate_seed_document(doc, load_audit_rows(s.audit_file))
    print(f"Seed file: {s.seed_file}")
    print(f"Questions: {result.question_count}")
    print("Per week:  " + ", ".join(f"W{w}={n}" for w, n in sorted(result.week_counts.items())))
    if not result.ok:
        print(f"FAILED: {len(result.errors)} error(s)")
        _print_errors(result.errors)
        return 1
    print("OK: 120 questions, 10 per week, 4 options each, exactly 1 verified correct option each, audit complete.")
    return 0


def cmd_seed() -> int:
    s = get_settings()
    with get_sessionmaker()() as session:
        try:
            summary = seed_database(session, s.seed_file, s.audit_file)
        except SeedValidationError as exc:
            session.rollback()
            print("FAILED: seed rejected; database left unchanged.")
            _print_errors(exc.errors)
            return 1
        session.commit()
    print(f"OK: seeded {summary['questions']} questions (deactivated {summary['deactivated']}).")
    print(f"Seed SHA-256: {summary['seed_sha256']}")
    return 0


def cmd_check_db() -> int:
    with get_sessionmaker()() as session:
        errors = validate_database(session)
    if errors:
        print(f"FAILED: {len(errors)} database integrity error(s)")
        _print_errors(errors)
        return 1
    print("OK: database holds 120 active questions, 10 per week, 4 options and 1 correct option each.")
    return 0


def cmd_release() -> int:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    print("Applying migrations...")
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    return cmd_seed() or cmd_check_db()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=["validate", "seed", "check-db", "release"])
    args = parser.parse_args(argv)
    return {
        "validate": cmd_validate,
        "seed": cmd_seed,
        "check-db": cmd_check_db,
        "release": cmd_release,
    }[args.command]()


if __name__ == "__main__":
    sys.exit(main())
