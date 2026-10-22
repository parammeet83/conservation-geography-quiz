# Conservation Geography Quiz

A web quiz built from the *Conservation Geography — Week 1–12 Assignment Solutions (2026)* question set: **120 multiple-choice questions**, 10 per week. Learners can practise any single week or take the full 120-question test. Questions and options are reshuffled on every new attempt, answers are saved as you go, and grading happens on the server.

Repository: <https://github.com/parammeet83/conservation-geography-quiz>

## Features

- **13 quizzes:** Week 1 – Week 12 (10 questions each) and an Overall Quiz (all 120 questions, each exactly once). Question counts on the home page come from the validated database.
- **Randomisation:** each new attempt gets a server-side Fisher–Yates shuffle of the question order and an independent shuffle of every question's four options. Display labels A–D are assigned after shuffling. Correctness is stored against the canonical option ID, never a position or letter.
- **Stable attempts:** both permutations are stored in PostgreSQL. Refreshing or reopening an attempt shows the same order and the saved answers. A new attempt is never created automatically.
- **Answering:** one answer per question, which you can change or clear. Previous/Next buttons, a question palette, answered and remaining counts, and per-answer *Saving… / Saved / Not saved (Retry)* status.
- **Submission:** a confirmation dialog shows answered and unanswered counts and warns about unanswered questions. Submission is blocked while any answer is unsaved. It is idempotent and transactional on the server, and the submitted attempt becomes read-only.
- **Results:** score, percentage (two decimals), and correct, incorrect, and unanswered counts. A question-by-question review shows your answer (or *Not answered*), the correct answer, and a status. You can filter the review and jump between questions. *Try again* starts a freshly shuffled attempt.
- **Security:** each attempt has a random access token. Only its SHA-256 hash is stored, it is sent as an `Authorization: Bearer` header, and it never appears in URLs or logs. Active-attempt responses contain no correctness data.
- **Accessible, responsive UI:** semantic radio groups, visible focus, a keyboard-operable focus-trapped dialog, state not conveyed by colour alone, and no horizontal scrolling at 360 px.

Not included (out of scope for this MVP): accounts, timers, negative marking, leaderboards, certificates, and explanations.

## Technology stack

| Layer | Implementation |
|---|---|
| Frontend | React 19, TypeScript 6, Vite 8, React Router 7, plain CSS (custom properties, light/dark) |
| Backend | Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2.1, Alembic, psycopg 3 |
| Database | PostgreSQL (tested with 17) |
| Tests | pytest (88 tests), Vitest + React Testing Library (14), Playwright (6 end-to-end) |
| Tooling | Ruff, ESLint, GitHub Actions CI |
| Data prep | PyMuPDF (maintainer-only PDF extraction script) |

## Architecture

```
Browser (React SPA) ──/api/v1 (JSON, Bearer token)──► FastAPI ──► PostgreSQL
                                                        │
          data/seed/questions.json ──(python -m app.cli seed, idempotent)──┘
                    ▲
scripts/extract_questions.py ◄── source PDF (one-time, maintainer only; not committed)
```

- **Question bank:** `questions` and `options`, with `options.is_correct` set from the PDF's bold formatting. A partial unique index allows at most one correct option per question.
- **Attempts:** `quiz_attempts` stores the token hash, mode, status, and score. `attempt_questions` stores the question order and selected answer. `attempt_question_options` stores the option order. Composite foreign keys guarantee that a displayed or selected option belongs to the same question.
- The running app reads only the database. It never parses the PDF.

## Repository structure

```
backend/                FastAPI app (app/), Alembic migrations (alembic/), tests (tests/)
frontend/               React app (src/), unit tests (tests/), Playwright tests (e2e/)
data/seed/              questions.json, answer_key_audit.csv, import_validation_report.md,
                        manual_visual_review.md
scripts/                extract_questions.py (PDF → seed), dev-db.ps1, setup.ps1,
                        start-backend.ps1, start-frontend.ps1, check-prereqs.ps1
docs/RUN_AND_VERIFY.md  Windows / PowerShell run and verification guide
.github/workflows/ci.yml
PRD.md, TRD.md, Backend_DB_Schema.md, UIUX_design_spec.md, WebAppFlow.md,
implementation_plan.md, INDEX.md   Product and technical specifications
```

## Installation (Windows, PowerShell)

Prerequisites: Python 3.12, Node.js 22 or 24, Git, and PostgreSQL 15+. The local setup reuses the binaries of an installed PostgreSQL and does not need Docker.

```powershell
git clone https://github.com/parammeet83/conservation-geography-quiz.git
cd conservation-geography-quiz
powershell -ExecutionPolicy Bypass -File scripts\check-prereqs.ps1
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

`setup.ps1` creates `.env` from `.env.example`, creates `backend\.venv`, installs the backend and frontend dependencies, and starts a project-local PostgreSQL cluster on port 5433 (`scripts\dev-db.ps1 init`). It then validates the question bank, runs the migrations, and seeds the database. Every step is safe to repeat.

`-ExecutionPolicy Bypass` on the command line applies only to that one process. Your machine's execution policy is not changed. The venv's `python.exe` is always called directly, so `Activate.ps1` is never needed.

The step-by-step equivalent of each script is in [docs/RUN_AND_VERIFY.md](docs/RUN_AND_VERIFY.md).

## Environment variables

Defined in `.env` at the repository root (copy from `.env.example`; never commit `.env`):

| Variable | Purpose | Default (local dev) |
|---|---|---|
| `DATABASE_URL` | App database (SQLAlchemy URL) | `postgresql+psycopg://cgq_app:cgq_local_dev@localhost:5433/cgq` |
| `TEST_DATABASE_URL` | Backend test database. Tests drop and recreate its schema, and it must differ from `DATABASE_URL`. | `…/cgq_test` |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API directly | `http://localhost:5173,http://127.0.0.1:5173` |
| `LOG_LEVEL` | Python log level | `INFO` |
| `VITE_API_BASE_URL` (frontend, optional) | API origin when the frontend is served separately from the API. Leave unset in development. | unset |

The local defaults are development-only credentials for a server that listens only on localhost.

## Database setup, migrations and seeding

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev-db.ps1 init   # create/start local cluster, role, cgq + cgq_test DBs
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head                   # apply migrations
.\.venv\Scripts\python.exe -m app.cli validate                       # validate seed files (no DB needed)
.\.venv\Scripts\python.exe -m app.cli seed                           # validate + idempotent upsert
.\.venv\Scripts\python.exe -m app.cli check-db                       # integrity checks against the DB
```

To use an existing PostgreSQL server instead, create a database and role yourself, set `DATABASE_URL` and `TEST_DATABASE_URL` in `.env`, and skip `dev-db.ps1`.

## Answer-key verification

The PDF is the only source of truth. `scripts/extract_questions.py` reads it with PyMuPDF and marks an option correct only when three independent checks agree:

1. **Font metadata:** the whole option is set in `Calibri,Bold`. Partial bolding is rejected.
2. **Rendered page:** the option's rasterised stroke width is at least 1.15× that of every other option in the question. The observed range is 1.26× to 1.60×.
3. **TRD cross-check:** the bold text matches the answer-key table in `TRD.md`.

In addition, all 26 rendered pages were compared manually with the extracted key ([data/seed/manual_visual_review.md](data/seed/manual_visual_review.md)).

Result: **120/120 questions verified, 0 unresolved** ([data/seed/import_validation_report.md](data/seed/import_validation_report.md), [data/seed/answer_key_audit.csv](data/seed/answer_key_audit.csv)).

`python -m app.cli validate` and `seed` fail if any of the following is true:

- The bank does not have exactly 120 questions, or a week does not have exactly 10.
- A question does not have four options or does not have exactly one correct option.
- Any text is blank.
- Any identity is duplicated.
- The audit file is incomplete or disagrees with the seed.
- Any question is not `verified`.

Source wording is preserved exactly, including repeated questions such as W3 Q2 / W7 Q9.

To regenerate the seed files (maintainers with the PDF only):

```powershell
py -3.12 -m pip install pymupdf
py -3.12 scripts\extract_questions.py --pdf "Conservation Geography Week 1 Solutions-merged.pdf"
```

The PDF is **not** committed to this public repository. The seed files are sufficient to run and validate the app.

## Running the application

Use two terminals:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1    # http://127.0.0.1:8000
powershell -ExecutionPolicy Bypass -File scripts\start-frontend.ps1   # http://localhost:5173
```

| URL | What |
|---|---|
| <http://localhost:5173> | The quiz app (Vite proxies `/api` to the backend) |
| <http://127.0.0.1:8000/api/v1/health> | Health check: `{"status":"ok","database":"ok"}` |
| <http://127.0.0.1:8000/docs> | Interactive OpenAPI documentation |

### API (base `/api/v1`)

| Method and path | Purpose |
|---|---|
| `GET /health` | Service and database status |
| `GET /quizzes` | 12 weekly quizzes plus Overall, with counts and availability from the DB |
| `POST /attempts` | `{"mode":"weekly","week_no":N}` or `{"mode":"overall"}` returns a shuffled attempt and an `access_token` (once) |
| `GET /attempts/{id}` | The stored attempt, with its order and selections. No correctness data. |
| `PUT /attempts/{id}/questions/{attempt_question_id}/answer` | `{"selected_option_id": uuid \| null}` saves or clears an answer |
| `POST /attempts/{id}/submit` | Grade and lock the attempt (idempotent). Returns the result and review. |
| `GET /attempts/{id}/result` | Result and review. Returns 409 before submission. |

Every attempt route requires `Authorization: Bearer <access_token>`. Errors use `{"error": {"code", "message", "details?"}}` with 401 (missing token), 403 (wrong token), 404 (unknown), 409 (invalid state), 422 (invalid input), and 503 (question bank invalid).

## Testing

```powershell
# Backend: lint, format, 88 tests (needs TEST_DATABASE_URL; tests rebuild that DB via migrations)
cd backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q

# Frontend: type check, lint, 14 component tests, production build
cd ..\frontend
npm run typecheck
npm run lint
npm test
npm run build

# End-to-end (Playwright; starts/reuses backend :8000 and Vite :5173; DB must be migrated + seeded)
npx playwright install chromium   # first time only
npm run test:e2e
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `running scripts is disabled on this system` | Run scripts as `powershell -ExecutionPolicy Bypass -File scripts\<name>.ps1`, and call `backend\.venv\Scripts\python.exe` directly instead of activating the venv. |
| Health shows `"database":"unavailable"` | Start the DB with `scripts\dev-db.ps1 start`, and check `DATABASE_URL` in `.env`. |
| Home page shows "Unavailable: question bank incomplete" | Run `python -m app.cli seed`, then `check-db`. |
| Port 5433, 8000, or 5173 already in use | Stop the other process, or use `dev-db.ps1 -Port <p>` and update `.env`. |
| "This attempt can't be opened" | The attempt's access key is stored only in the browser that started it. Start a new attempt from the home page. |
| Backend tests are skipped | Set `TEST_DATABASE_URL` in `.env` (it must differ from `DATABASE_URL`). |
| `pg_ctl`/`initdb` not found | Install PostgreSQL, or pass `-PgBin "C:\Program Files\PostgreSQL\17\bin"` to `dev-db.ps1`. |

Stop the local database with `powershell -ExecutionPolicy Bypass -File scripts\dev-db.ps1 stop`.

## Design notes and known limitations

- The attempt token is kept in the browser's `localStorage` so an attempt survives refreshes and restarts. Anyone with access to the same browser profile could resume or submit that attempt. That is acceptable for an anonymous practice quiz, but don't treat it as authentication.
- The seed file and audit CSV, committed here, necessarily contain the answer key. The protection guarantee is that the **running app and API** never reveal correctness before submission.
