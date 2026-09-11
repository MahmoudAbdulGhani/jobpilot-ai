# JobPilot AI

A private, AI-powered job-search dashboard: track job opportunities, analyze how well
they match your CV, generate truthful tailored cover letters, and manage applications
from discovery through offer.

Standalone companion project to my portfolio application. The portfolio remains the
source of the latest approved CV; JobPilot owns everything else.

## Status

Phase 1e - single-owner authentication (Argon2id password hashing, JWT access tokens,
rotating refresh tokens, CSRF-protected cookie logout, owner-setup CLI).

## Tech stack

- Backend: Python 3.11+, FastAPI, Pydantic / Pydantic Settings
- Frontend (later phase): Next.js, TypeScript, Tailwind CSS
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

Directories such as `models/`, `schemas/`, `services/`, `repositories/`, `agents/`
are added in later phases when first needed.

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

## Roadmap

1. Backend foundation (config, database, auth)
2. Jobs and application tracking
3. CV integration with the portfolio
4. AI job analysis (provider-independent, Ollama first)
5. Cover letter generation
6. Controlled JobPilot agent with approvals and audit logging
