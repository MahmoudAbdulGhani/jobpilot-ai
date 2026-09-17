# Discovery and test-isolation closeout — 2026-09-17

## Incident findings

The affected target was **`jobpilot_test` at `127.0.0.1:5433`**, shared by backend
and browser tests. This identification follows the retained regression invocation,
the `test_engine` fixture's use of `settings.test_database_url`, and the local
configuration (only host, port and database names were inspected). The separate
development database is `jobpilot` on the same server. No database connections or
database modifications were made during this closeout.

Evidence reviewed:

- `storage/discovery-regressions.txt`: the earlier regression selection completed
  successfully, including `test_saved_jobs_migration.py`.
- The prior invocation set `JOBPILOT_TEST_PRESERVE_DB=1`. At that time the flag
  bypassed fixture truncation, but did not stop the test's own downgrade.
- `test_saved_jobs_migration_preserves_existing_authentication_record` configured
  Alembic with the shared test engine URL, called `downgrade(..., 299fe1eaa3f0)`,
  inserted a temporary authentication row, upgraded to head, checked/deleted that
  temporary row, and upgraded to head again in `finally`.
- The migration chain drops discovery columns/indexes, application status events,
  applications, AI usage, pack operations/versions/packs, fit analyses, profile
  suggestions, resume extractions, resumes, candidate profiles and saved jobs.
  The target revision retains the `users` and `refresh_tokens` tables.

Any rows present in those dropped tables would have been lost. Re-upgrading
recreated schema, not records. The successful assertion only concerns the
temporary user inserted **after** the downgrade; it does not prove pre-existing
data survived. No pre-incident snapshot, row inventory or database audit log was
retained, so the number and identity of lost records remain **unknown**. Current
table contents cannot establish historical loss. No recovery is claimed or
attempted. That migration test was not executed again in this closeout.

## Fail-closed test isolation

The persistent `test_engine` fixture now only constructs an engine; it performs
no automatic migration or truncation. The reset helper was removed. Normal tests
continue using transactions for their own work. A test database's schema must be
provisioned separately rather than changed implicitly by running pytest.

The four destructive migration tests now carry a `destructive_database` marker
and use **`disposable_engine`**, never the shared test engine. Without explicit
opt-in they are skipped before fixtures execute. Partial/invalid opt-in aborts
collection. The disposable fixture checks authorization before any connection or
migration. A separate, already provisioned disposable database is required:

- `JOBPILOT_ALLOW_DESTRUCTIVE_TESTS=1`
- `JOBPILOT_DISPOSABLE_DATABASE_URL`: private PostgreSQL+psycopg URL for that database
- Database name must match `jobpilot_disposable_[a-z0-9_]+`
- `JOBPILOT_DISPOSABLE_DATABASE_CONFIRM`: that exact database name
- `JOBPILOT_TEST_PRESERVE_DB=1` must **not** be set; it always vetoes destructive use

Do not place credentials in committed files or command-line arguments. Supply a
private process environment/secret store. No disposable database was created or
used during this task, and no destructive opt-in was enabled.

Both configured persistent database names, the default development/browser names,
system databases, URL query overrides and unconfirmed names are rejected. Merely
changing host or adding the marker cannot authorize a persistent database. These
are explicit operator attestation and target-isolation checks, not an assertion
that a database with a particular name contains no valuable records.

Runtime pytest guards also check Alembic downgrade targets and SQLAlchemy
DROP/TRUNCATE statements (including reset SQL inside DO blocks), even when a
marker is missing or the target is switched. These guards are test-harness
protections, not a database permission boundary or a restriction on external
administrative tools. The positive authorization tests use fake URLs and never
execute destructive SQL.

## Bounded live JobTech smoke check

[Timestamped report](../evidence/jobtech-live-smoke-20260917-091322Z.json), started
at **2026-09-17 09:13:22 UTC**. This is live-source evidence, separate from the
earlier mocked adapter and browser tests.

Official [open-data policy](https://arbetsformedlingen.se/other-languages/english-engelska/about-the-website/apis-and-open-data)
and [JobSearch documentation](https://jobsearch.api.jobtechdev.se/) were checked.
The live Swagger contract was version 1.37.0, with CC0 ads and no API security
requirement. The documented remote parameter remains phrase matching. No numeric
rate allowance is assumed; this smoke was deliberately limited to four sequential
requests, with zero retries, no redirects, no credentials and no paid service.

| Request | Result |
| --- | --- |
| GET `/swagger.json` | HTTP 200; contract and license checked |
| GET `/search?q=Python&sort=pubdate-desc&offset=0&limit=20&resdet=full` | HTTP 200; production parser accepted all 20 results; reported total 724 |
| GET `/ad/31488391` | HTTP 200; production preview parser accepted the same source identity |
| HEAD canonical Platsbanken source link for `31488391` | HTTP 200; no redirect followed or page body retained |

Sample: **DevOps Engineer**, **Memlist AB**, source location
`Stockholm, Stockholms län, Sverige`. Publication date `2026-09-17T11:06:20`,
deadline `2026-10-17T23:59:59`, plain-text description length 4,848 characters,
workplace label `Arbete på plats`; salary was not supplied. Source dates are
retained as provided, without inferring timezone. All 20 normalized links used
the canonical source URL format; only the sample link was checked over HTTP.
No complete ad/contact bodies, credentials or unrestricted errors were retained.

This establishes current endpoint access and successful parsing for one search
page and one preview. It does not establish all-query reliability, job accuracy,
future availability, actual salary or applicant eligibility. The remote filter
was not live-tested. No jobs were imported and no AI calls or applications were
made.

## UI and focused verification

Discovery explicitly says **primarily Swedish coverage**, labels remote matches
**approximate**, and states that remote does **not** imply worldwide eligibility.
Users are asked to verify work location, residency and work authorization with
the employer. Existing missing-field labels and plain-text rendering are retained.

- **23 safety tests passed**, with database connection creation blocked. Tests
  cover absent/invalid opt-in, persistent/system targets, confirmation mismatch,
  preservation veto, target switching, runtime Alembic and SQLAlchemy guards, and
  absence of migration/reset work in the persistent fixture.
- **4 destructive tests skipped**: saved jobs (1), candidate profile (1), resumes
  (2). Their migration/data-retention behavior on a disposable database remains
  unverified; skip is not a pass. No destructive migration or reset was executed.
- **7 discovery component tests passed**, including geography/remote disclosure.
  Affected-file ESLint and TypeScript checks passed.
- No database-backed/browser workflow was rerun: the changes are test guards and
  disclosure text, covered without touching persistent database contents.

Commands (backend from repository root; frontend from `frontend`):

```powershell
$env:JOBPILOT_ALLOW_DESTRUCTIVE_TESTS='0'
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_database_safety.py backend/tests/test_saved_jobs_migration.py backend/tests/test_candidate_profile_migration.py backend/tests/test_resumes_migration.py -o addopts= -q -rs
npm test -- --run tests/discovery.test.tsx
npx eslint components/Discovery.tsx tests/discovery.test.tsx
npx tsc --noEmit
```

Original reports and unrelated work were preserved. No database downgrade/reset,
recovery, push, deployment, Jira action or additional provider integration occurred.
