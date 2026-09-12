# JobPilot AI

A private, AI-powered job-search dashboard: track job opportunities, analyze how well
they match your CV, generate truthful tailored cover letters, and manage applications
from discovery through offer.

Standalone companion project to my portfolio application. The portfolio remains the
source of the latest approved CV; JobPilot owns everything else.

## Status

Connected FastAPI/PostgreSQL backend and Next.js Career Journal frontend with
single-owner authentication and private saved-job CRUD, filtering, search,
archiving, and pagination.

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

Connected browser verification uses Playwright Chromium and a backend explicitly
pointed at the guarded `jobpilot_test` database. With both local services running:

```powershell
cd frontend
npm run test:e2e
```

The final verification completed 91 backend tests and 2 connected browser tests.
Coverage includes login and reload restoration, persisted CRUD, nullable-field
clearing, notes, server search and pagination, archive/restore, deletion
cancel/confirm, logout, missing IDs, mobile dialog behavior, and two-user isolation.
Screenshots and the normalized option-2 comparison are under `evidence/`.

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

## Roadmap

1. Backend foundation (config, database, auth)
2. Jobs and application tracking
3. CV integration with the portfolio
4. AI job analysis (provider-independent, Ollama first)
5. Cover letter generation
6. Controlled JobPilot agent with approvals and audit logging
