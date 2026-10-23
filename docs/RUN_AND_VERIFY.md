# Run and Verify — Windows 10/11, VS Code, PowerShell

This guide runs the Conservation Geography Quiz locally and verifies every major behaviour. Commands are for **Windows PowerShell 5.1** (the default) and also work in PowerShell 7. Run them in the VS Code terminal (**Terminal → New Terminal**).

> **Execution policy.** Nothing here asks you to change your machine's policy. Scripts run with `powershell -ExecutionPolicy Bypass -File …`, which applies only to that single process. The Python virtual environment is never activated; commands call `.\.venv\Scripts\python.exe` directly, so `Activate.ps1` is not needed.

---

## 1. Check software versions

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-prereqs.ps1
```

**Expected:** `[ OK ]` lines for Python 3.12, Node.js, npm, Git, and PostgreSQL, ending with `All required tools found.` Docker is optional and may show `[ -- ]`.

If something is missing, install it and re-run the check:

- Python 3.12: <https://www.python.org/downloads/windows/>. Tick *Add python.exe to PATH*; this also installs the `py` launcher.
- Node.js 22 or 24 LTS: <https://nodejs.org/>
- PostgreSQL 15 or later: <https://www.postgresql.org/download/windows/>. The setup only needs its binaries (`initdb`, `pg_ctl`, `psql`); you don't need the `postgres` superuser password.

You can also check each tool by hand:

```powershell
py -3.12 --version; node --version; npm --version; git --version
& "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" --version
```

## 2. Open the project directory

```powershell
cd $HOME\Desktop\MyProjects\conservation-geography-quiz   # or wherever you cloned it
code .
```

**Expected:** VS Code opens with `backend\`, `frontend\`, `data\`, `docs\`, and `scripts\` in the Explorer. All later commands run from this repository root unless a step says `cd`.

## 3. Create the Python environment

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe --version
```

**Expected:** `Python 3.12.x`. The folder `backend\.venv\` is created; it is git-ignored.

## 4. Install dependencies

```powershell
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
cd frontend; npm install; cd ..
```

**Expected:** pip finishes without errors (FastAPI, SQLAlchemy, Alembic, psycopg, pytest, Ruff). npm reports `added … packages` and creates `frontend\node_modules\`.

> **Shortcut:** `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` performs steps 3–8 in one go and is safe to re-run.

## 5. Configure environment variables

```powershell
Copy-Item .env.example .env
notepad .env   # optional: review the values
```

**Expected:** `.env` exists in the repository root with `DATABASE_URL`, `TEST_DATABASE_URL`, `CORS_ORIGINS`, and `LOG_LEVEL`. The defaults point to the local cluster from step 6. `.env` is git-ignored and must never be committed.

## 6. Start PostgreSQL

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev-db.ps1 init
powershell -ExecutionPolicy Bypass -File scripts\dev-db.ps1 status
```

**Expected:**

- The first run prints `Initialised cluster in …\.local\pgdata`, `PostgreSQL started on localhost:5433`, `Created role cgq_app`, `Created database cgq`, and `Created database cgq_test`.
- Later runs say the cluster and objects already exist.
- `status` prints `Running on localhost:5433`.

This is a private cluster in `.local\pgdata`, listening on localhost only. It does not touch any PostgreSQL Windows service you already run.

If PostgreSQL is installed somewhere other than `C:\Program Files\PostgreSQL\<version>`, add `-PgBin "D:\path\to\PostgreSQL\17\bin"`.

**Using your own PostgreSQL server instead:** create a role and two databases, put their URLs in `.env`, and skip `dev-db.ps1`. For example, in `psql -U postgres`:

```sql
CREATE ROLE cgq_app LOGIN PASSWORD 'choose-a-password';
CREATE DATABASE cgq OWNER cgq_app;
CREATE DATABASE cgq_test OWNER cgq_app;
```

**Using Docker instead** (if installed):

```powershell
docker run -d --name cgq-db -e POSTGRES_USER=cgq_app -e POSTGRES_PASSWORD=cgq_local_dev -e POSTGRES_DB=cgq -p 5433:5432 postgres:17
docker exec cgq-db psql -U cgq_app -d cgq -c "CREATE DATABASE cgq_test"
```

## 7. Migrate and seed the database

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.cli seed
.\.venv\Scripts\python.exe -m app.cli seed      # run twice: proves seeding is idempotent
.\.venv\Scripts\python.exe -m app.cli check-db
cd ..
```

**Expected:**

- Alembic prints `Running upgrade -> 0001_initial_schema` the first time, and nothing new afterwards.
- Each `seed` prints `OK: seeded 120 questions (deactivated 0).` and the same SHA-256. Re-running it creates no duplicates, because question and option IDs are stable UUIDs.
- `check-db` prints `OK: database holds 120 active questions, 10 per week, 4 options and 1 correct option each.`

## 8. Validate the question bank

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.cli validate
cd ..
```

**Expected:**

```
Questions: 120
Per week:  W1=10, W2=10, … W12=10
OK: 120 questions, 10 per week, 4 options each, exactly 1 verified correct option each, audit complete.
```

The exit code is non-zero on any structural error, audit mismatch, or unverified answer. The answer-key evidence is in:

- `data\seed\import_validation_report.md`: method, counts, and checks (120 verified, 0 unresolved).
- `data\seed\answer_key_audit.csv`: one row per question with week, number, PDF page, correct option text, and the font, rendered-stroke, TRD, and manual-review checks.
- `data\seed\manual_visual_review.md`: the page-by-page human comparison.

Optional, only if you have the source PDF in the repository root: regenerate the seed files from the PDF.

```powershell
py -3.12 -m pip install pymupdf
py -3.12 scripts\extract_questions.py --pdf "Conservation Geography Week 1 Solutions-merged.pdf"
```

**Expected:** `Extracted 120 questions from 26 pages … Verified: 120  Unresolved: 0  Global issues: 0`. The script exits non-zero if anything is unresolved.

## 9. Start the backend and frontend (two terminals)

**Terminal 1 (backend):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1
```

**Expected:** `Uvicorn running on http://127.0.0.1:8000`. Leave it running.

**Terminal 2 (frontend).** Click **+** in the VS Code terminal panel, then:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-frontend.ps1
```

**Expected:** `VITE … ready` and `Local: http://localhost:5173/`. Leave it running.

The scripts are equivalent to:

```powershell
cd backend;  .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend; npm run dev
```

## 10. Open the application

Open <http://localhost:5173>.

**Expected:**

- The heading reads **Conservation Geography Quiz**, with the line "Choose a week to practice or take the full 120-question test."
- A highlighted **Overall Quiz** card shows *120 questions*.
- Twelve cards, **Week 1** to **Week 12**, each show *10 questions*. These counts come from the database.

If the database is down, you see an error with a **Retry** button instead of empty counts.

## 11. Check the API health endpoint

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/quizzes | ConvertTo-Json -Depth 4
```

**Expected:** `status : ok` and `database : ok`. The catalogue lists 12 weeks with `question_count = 10` and `available = True`, and `overall.question_count = 120`. With the database stopped, `/health` returns HTTP 503 with `"database":"unavailable"`.

Interactive API docs are at <http://127.0.0.1:8000/docs>.

## 12. Run all test suites

With the database running (step 6) and from the repository root:

```powershell
# Backend: lint + format + 104 tests. Rebuilds cgq_test from migrations each run.
cd backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q
cd ..

# Frontend: types, lint, 26 component tests, production build
cd frontend
npm run typecheck
npm run lint
npm test
npm run build

# End-to-end: real browser, real API and DB
npx playwright install chromium     # first time only (~120 MB download)
npm run test:e2e
cd ..
```

**Expected:**

- Ruff: `All checks passed!` and `… files already formatted`. Alembic check: `No new upgrade operations detected.`
- pytest: `104 passed` (including 16 Study Mode tests). The suite covers seed validation, the TRD cross-check, idempotent seeding, DB constraints, all 12 weekly scopes, overall coverage, deterministic shuffle replay, the correct answer at A/B/C/D, rounding, invalid and cross-question options, duplicate and concurrent submits, immutability, token checks, absence of answer-key leaks, logging without tokens, and CORS.
- Vitest: `26 passed` (including 12 Study Mode tests). Vite build: `✓ built`.
- Playwright: `9 passed`. These cover Study Mode (weekly journey, overall, 360 px),  the weekly journey, Week 12 scope, the overall journey with all 120 questions, fresh shuffles, no overflow at 360 px, and keyboard use.

Playwright reuses the servers from step 9 if they are running; otherwise it starts them.

## 13. Complete a weekly quiz

1. On the home page, click **Week 1**. **Expected:** the URL becomes `/attempts/<uuid>` (no token in it), the heading shows *Question 1 of 10*, and the progress line reads *0 answered · 10 remaining*.
2. Select an option. **Expected:** the row highlights in neutral green (never red or green "correct" colours), the footer shows *Saving…* then *✓ Answer saved*, the progress updates, and palette button 1 shows a ✓.
3. Use **Next →**, **← Previous**, and the numbered **Go to question** palette. **Expected:** answers stay selected when you return to a question. **Previous** is disabled on question 1 and **Next** on question 10.
4. Change an answer, and use **Clear selection** on another. **Expected:** both changes are saved, and the counts update.
5. Repeat with a different week, for example **Week 7**. **Expected:** only that week's ten questions appear.

### 13a. Use Study Mode

1. On the home page, select **Study Mode** in the *Mode* group (Quiz Mode is selected by default), then click **Week 1**. **Expected:** the scope line reads *Week 1 · Study Mode*, a tally shows *0 correct · 0 incorrect*, and no answer is highlighted.
2. Choose an option. **Expected:** the options lock; the correct option turns green with *✓ Correct answer*; if you chose wrongly your option turns red with *✗ Your answer* and the message reads *Incorrect. The correct answer is …*; otherwise *Correct!*. Clicking another option changes nothing.
3. Answer all ten. **Expected:** *Study session complete* with your correct/incorrect counts; **See full summary** opens *Study session summary* with the score and the full review. **Try again** starts a new Study Mode attempt.
4. Repeat with **Overall Quiz** in Study Mode, and check that Quiz Mode still shows no correctness until submission.

## 14. Complete the overall quiz

1. From the home page, click **Overall Quiz**. **Expected:** *Question 1 of 120*; the palette has 120 numbered buttons (collapsible under **Go to question** on phones).
2. Answer a question near the start, jump to 60 and answer it, then jump to 120 and answer it. **Expected:** *3 answered · 117 remaining*, and **Next** is disabled on question 120.
3. Optional: step through with **Next** to confirm that every question appears once. The automated e2e test compares all 120 against the seed file.

## 15. Check randomisation and answer persistence

1. Start **Week 1**, note the first question and the order of its options, then return to the home page and click **Start new** on Week 1.
   **Expected:** the new attempt has a different URL, and usually a different question order and different option orders. Each question's four options are shuffled independently, and labels A–D are reassigned.
   A coincidental identical order is possible, but rare: about 1 in 10! for question order.
2. While answering, watch the save status. To simulate a failure, stop the backend (Ctrl+C in Terminal 1) and select an option.
   **Expected:** *⚠ Not saved … Retry* appears, the palette button shows **!**, and your selection stays on screen.
3. Restart the backend and click **Retry** (or **Retry saving**). **Expected:** *✓ Answer saved*.
4. While an answer is unsaved, open **Submit quiz**. **Expected:** the dialog warns that answers are not saved, and its **Submit quiz** button is disabled until they are.

## 16. Refresh and resume an attempt

1. In an attempt with some answers, press **F5**. **Expected:** the same question number (kept in `?q=`), the same question and option order, the same selections, and the same counts. No new attempt is created.
2. Close the tab, reopen <http://localhost:5173>. **Expected:** that week's card shows **Resume** and **Start new**. **Resume** returns to the same attempt.
3. Open the attempt URL in a private window, or another browser. **Expected:** *This attempt can't be opened*, with a link back to quiz selection. No attempt is created. The access key exists only in the browser that started the attempt.

## 17. Submit and review results

1. Click **Submit quiz**. **Expected:** a dialog shows *Answered* and *Unanswered* counts, and *You have N unanswered questions. Submit anyway?* if any are blank. **Review answers** (or Esc) returns to the quiz without submitting.
2. Click **Submit quiz** in the dialog. **Expected:** the button shows *Submitting…* and cannot be pressed twice. Then **Your results** opens and shows:
   - the score as *correct / total* (out of 10 or 120) and a percentage to two decimals (for example *1 / 120* gives *0.83%*);
   - Total, Correct, Incorrect, and Unanswered counts;
   - for every question, its text, *Your answer* (or *Not answered*), *Correct answer*, and a **Correct**, **Incorrect**, or **Unanswered** badge (icon plus text);
   - filter chips, and jump links for long reviews.
3. Press **F5** on the results page. **Expected:** the same results. Going back to the attempt URL redirects to the results; a submitted attempt can't be edited (the API returns 409).
4. Click **Try again**. **Expected:** a new, freshly shuffled attempt of the same quiz with 0 answered. **Back to quiz selection** returns home.

Optional API check that grading happens on the server and that tokens are enforced:

```powershell
$a = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/attempts -ContentType 'application/json' -Body '{"mode":"weekly","week_no":2}'
$a.questions[0] | ConvertTo-Json -Depth 3   # only id/label/text per option - no correctness fields
try { Invoke-RestMethod "http://127.0.0.1:8000/api/v1/attempts/$($a.id)" } catch { $_.Exception.Response.StatusCode }   # 401 Unauthorized (no token)
$h = @{ Authorization = "Bearer $($a.access_token)" }
try { Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/attempts/$($a.id)/submit" -Headers $h -ContentType 'application/json' -Body '{"score_correct":10}' } catch { $_.Exception.Response.StatusCode }   # 422: client scores rejected
(Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/attempts/$($a.id)/submit" -Headers $h).score_correct   # 0 (nothing answered)
```

## 18. Stop services safely

- In Terminals 1 and 2, press **Ctrl+C** to stop the backend and Vite.
- Stop the local database:

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\dev-db.ps1 stop
  ```

  **Expected:** `PostgreSQL stopped.` Data persists in `.local\pgdata`; next time, run `dev-db.ps1 start`.
- To wipe all local data, stop the cluster, delete `.local\`, and run step 6 again.

## 19. Check the pushed code and CI status on GitHub

```powershell
git status
git remote -v
git log -3 --oneline
git fetch origin; git status -sb       # expect: ## main...origin/main (no ahead/behind)
git ls-remote origin main              # remote commit hash; must equal: git rev-parse HEAD
git rev-parse HEAD
```

Then open:

- Code: <https://github.com/parammeet83/conservation-geography-quiz>. **Expected:** README rendered, plus `backend/`, `frontend/`, `data/seed/`, `docs/`, `scripts/`, and `.github/workflows/`. There is no PDF, `.env`, `node_modules`, `.venv`, or `.local`.
- CI: <https://github.com/parammeet83/conservation-geography-quiz/actions>. **Expected:** the **CI** workflow runs on each push to `main`, with three jobs:
  - **Backend:** Ruff, seed validation, migrations, `alembic check`, seeding twice, `check-db`, a downgrade/upgrade round trip, and pytest against a PostgreSQL 17 service.
  - **Frontend:** typecheck, lint, Vitest, and build.
  - **End-to-end:** Playwright against the full stack.

  A green check means all three passed. If a job fails, open it to see the log; Playwright failures upload a `playwright-report` artifact.

---

### Security note on attempt access

Each attempt has a random 256-bit access token. The server stores only its SHA-256 hash. The browser keeps the token in `localStorage` and sends it as an `Authorization: Bearer` header; it never appears in URLs or server logs. Anyone using the same browser profile can resume that attempt. That fits an anonymous practice quiz, but it is not user authentication.
