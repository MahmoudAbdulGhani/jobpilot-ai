# JobPilot AI

A private, AI-powered job-search dashboard: track job opportunities, analyze how well
they match your CV, generate truthful tailored cover letters, and manage applications
from discovery through offer.

Standalone companion project to my portfolio application. The portfolio remains the
source of the latest approved CV; JobPilot owns everything else.

## Status

Connected FastAPI/PostgreSQL backend and Next.js Career Journal frontend with
single-owner authentication, private saved-job CRUD with filtering, search,
archiving, and pagination, and a private candidate profile for the job-search
snapshot.

## Tech stack

- Backend: Python 3.11+, FastAPI, Pydantic / Pydantic Settings
- Frontend: Next.js App Router, TypeScript, Newsreader, DM Sans, Phosphor icons
- Database (Phase 1b): PostgreSQL via Docker Compose, SQLAlchemy, Alembic
- Testing: pytest

## Repository layout

```
jobpilot-ai/
├── backend/
│   ├── app/
│   │   ├── api/routes/    # HTTP route handlers
│   │   └── core/          # configuration and app-wide plumbing
│   └── tests/
├── .env.example           # template - copy to .env, never commit real secrets
└── README.md
```

Domain models, validation schemas, services, and API routes live under `backend/app/`.

## Local development (backend)

Start PostgreSQL from the repository root:

```powershell
docker compose up -d db
docker compose ps
```

Then configure, migrate, and run the backend:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item ..\.env.example ..\.env   # then edit .env: set SECRET_KEY

.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Create the single owner account (interactive; the password is never echoed or stored
in command history):

```powershell
.\.venv\Scripts\python.exe -m app.cli setup-owner
```

JobPilot is strictly single-user: once an owner exists, further `setup-owner` runs are refused.

- API: http://127.0.0.1:8000/api/health
- Docs: http://127.0.0.1:8000/api/docs

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The test suite refuses to use the development database and targets the database
named by `POSTGRES_TEST_DB`.

## Local development (frontend)

Use `localhost` for both services; do not mix it with `127.0.0.1`, because the
refresh and CSRF cookies are host-scoped. After the backend and owner account are
ready, open a second PowerShell window from the repository root:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- API docs: http://localhost:8000/api/docs

`NEXT_PUBLIC_API_URL` is the non-secret browser-visible API base and defaults to
`http://localhost:8000/api`. Keep backend secrets only in the repository-root
`.env`; never use a `NEXT_PUBLIC_` variable for them.

The access token is held only in browser memory. The backend owns the HttpOnly
`jobpilot_refresh` cookie and readable `jobpilot_csrf` cookie. The frontend sends
credentials with API calls, restores sessions through `/api/auth/refresh`, sends
the matching `X-CSRF-Token` on refresh/logout, coordinates concurrent refreshes,
and retries an authenticated request at most once. Production still requires
HTTPS with `AUTH_COOKIE_SECURE=true`.

Frontend checks:

```powershell
cd frontend
npm run typecheck
npm run lint
npm run build
```

Connected browser verification uses Playwright Chromium. The harness starts its
own frontend on port 3010 and backend on port 8010; those ports must be free. It
sets `POSTGRES_DB` to `POSTGRES_TEST_DB` and explicitly enables
`E2E_TEST_MODE=true` only for that guarded backend process. Do not enable this
flag on the development server. Both conditions are required for the bootstrap
and cleanup endpoints; otherwise they return `404`. Cleanup also requires the
random password generated for that run, so it cannot delete another run's records.

```powershell
cd frontend
npm run test:e2e
```

The final verification completed 180 backend tests, 22 frontend component tests,
and 5 connected browser tests.
Coverage includes login and reload restoration, persisted CRUD, nullable-field
clearing, notes, server search and pagination, archive/restore, deletion
cancel/confirm, logout, missing IDs, mobile dialog behavior, two-user isolation,
and the connected candidate profile workflow (empty state, create and persist,
reload, client validation, second-user isolation). Screenshots and the normalized
option-2 comparison are under `evidence/`.

## Resume library

The resume library stores each candidate's original file bytes verbatim and
serves only the owner:

- `POST /api/resumes` accepts a multipart upload and stores the exact bytes from
  the client (no rewriting, re-encoding, or text re-extraction on the server).
- `GET /api/resumes` lists the saved resumes; `PATCH /api/resumes/{id}` sets the
  primary resume or renames it; `DELETE /api/resumes/{id}` removes a resume.
- `GET /api/resumes/{id}/download` streams the original bytes back with the
  original filename, so a downloaded DOCX is byte-for-byte the uploaded DOCX.

This is what "DOCX→blob" means in the code: the frontend reads the local upload
(original bytes → browser `Blob`), uploads it to the private endpoint, and the
backend persists those bytes as an opaque blob. Validation inspects only the
magic header and bounded ZIP/XML structure to accept `application/pdf` and
`application/vnd.openxmlformats-officedocument.wordprocessingml.document`; it
never transforms or silently rewrites a file, and unsupported files are rejected
with `415` rather than being altered.

### Resume text extraction and review

Each owned PDF or DOCX has an explicit **Extract text** action. Extraction runs
locally on the JobPilot backend using `pypdf` for PDFs and `python-docx` for
DOCX files; it does not call AI services, resolve external resources, execute
document content, change the uploaded bytes, or update the candidate profile.
PDF output retains page markers, while DOCX output includes paragraphs and
tables in document order.

The original extraction and an editable review draft are stored separately.
Saving an edit marks the draft unreviewed; **Confirm text** records an explicit
review timestamp. Repeating extraction never overwrites a successful or reviewed
record, while failed attempts can be retried. Deleting the source resume also
deletes its derived extraction record.

Extraction is bounded by the uploaded-file limit plus
`RESUME_EXTRACTION_TIMEOUT_SECONDS`, `RESUME_EXTRACTION_MAX_CHARS`,
`RESUME_EXTRACTION_MAX_PAGES`, and `RESUME_EXTRACTION_MAX_BLOCKS`; defaults are
documented in `.env.example`. Encrypted or malformed files and documents that
exceed these limits produce a visible failure state. Image-only/scanned PDFs
require OCR and are reported as such; OCR is intentionally outside this milestone.

### AI profile suggestions

After confirming extracted CV text, choose **Suggest profile details with AI**.
JobPilot shows the configured provider, proposed values, and exact supporting
passages together. Select and edit the facts you accept, then use **Apply selected
changes**; generation alone never changes the candidate profile. Supported fields
are headline, candidate location, skills, experience, education, and languages.
Target roles, salary, remote preference, and work authorization remain manual.

AI is disabled by default. To opt in, set `JOBPILOT_AI_ENABLED=true`, choose a
Structured-Outputs-capable `JOBPILOT_AI_MODEL`, and set
`JOBPILOT_OPENAI_API_KEY` in the private repository-root `.env`. The adapter uses
the official OpenAI Python SDK and Responses API with Structured Outputs,
`store=false`, no tools, a request timeout, no SDK retries, and bounded input and
output. Confirmed CV text leaves JobPilot only after the explicit generation
action. `store=false` disables response-object storage but is not described here
as a zero-retention guarantee; review OpenAI's current API data controls before
enabling the service.

Lists append selected entries and skip exact normalized duplicates; they are
never fuzzily merged or automatically removed. Scalars show explicit replacement.
Apply is atomic and rejects stale profile or confirmed-CV revisions. Accepted
facts retain provenance; later manual field edits relabel that field as user-edited.
Deleting the source CV removes suggestion snapshots while retaining applied profile
values with the source marked unavailable and without retained evidence quotes.

The deterministic provider is available only when both `E2E_TEST_MODE=true` and
`JOBPILOT_AI_TEST_PROVIDER=true` run against `POSTGRES_TEST_DB`; it is never a
normal-server fallback. Live OpenAI behavior and suggestion quality remain
unverified. After configuring the service, an owner may separately opt into a
smoke test using a synthetic CV; never use a real CV for initial validation.

## Saved jobs API

Saved jobs belong to the authenticated user. Source URLs are stored only as bookmarks;
JobPilot does not fetch or scrape them. Different users may save the same URL.

Input limits are 200 characters for title and company, 300 for location, 50,000 for
the job description, 2,048 for an HTTP/HTTPS source URL, and 20,000 for personal
notes. List searches are limited to 200 characters, and page size is 1–100.

To try the workflow in Swagger at http://127.0.0.1:8000/api/docs:

1. Call `POST /api/auth/login` with the local owner credentials.
2. Copy the returned access token, choose **Authorize**, and enter the token value.
3. Call `POST /api/jobs` with a request such as:

   ```json
   {
     "title": "Backend Engineer",
     "company": "Example Systems",
     "location": "Remote",
     "description": "Build and maintain reliable APIs.",
     "source_url": "https://careers.example.com/jobs/backend-engineer",
     "notes": "Review the platform requirements before applying."
   }
   ```

4. Call `GET /api/jobs`; active jobs are returned by default. Use
   `?archived=true`, `?search=backend`, `?page=1`, and `?page_size=20` as needed.
5. Call `PATCH /api/jobs/{job_id}` to edit it or send
   `{"is_archived": true}` to archive it. Use `DELETE` to permanently remove it.

## Candidate profile API

The candidate profile is a private snapshot owned by the signed-in user:

- `GET /api/profile` returns the profile, or `404` before it has been created.
- `PATCH /api/profile` upserts it: partial updates merge with saved values, and
  fields sent as `null` are cleared. An empty `{}` payload is valid for
  updating other fields in parallel before any profile exists.

Supported fields: `headline` (≤200), `target_roles` (≤10), `location` (≤300),
`remote_preference` (`office|hybrid|remote`), `work_authorization`
(`citizen|permanent_resident|work_visa|needs_sponsorship|other`), `skills`
(≤50 of ≤100 chars), `experience` (≤20 `{title, organization, period, notes}`),
`education` (≤10 `{school, degree, field, period}`), `languages`
(≤15 `{name, proficiency}` with proficiency
`basic|conversational|professional|native`), and `salary_preference`
(`{currency, min, max}` with `min ≤ max`). Empty optional strings normalize to
`null`, matching the jobs API convention.

## Roadmap

1. Backend foundation (config, database, auth)
2. Jobs and application tracking
3. CV integration with the portfolio
4. AI job analysis (provider-independent, Ollama first)
5. Cover letter generation
6. Controlled JobPilot agent with approvals and audit logging
