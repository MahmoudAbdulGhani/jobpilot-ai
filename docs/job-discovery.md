# Job discovery and reviewed import

For the subsequent Jobicy expansion, current source-selection research, shared cache,
eligibility semantics and live/mock evidence, see [International discovery](discovery-international.md).

Implemented on `feat/job-discovery-reviewed-import`, starting from `a8cdd10`.

This document records the initial `ee5cf56` milestone. The subsequent
[closeout](discovery-closeout.md) replaces its preservation-mode setup with
fail-closed disposable-database isolation and adds bounded live-source evidence.

## Source and permitted access

Selected **JobTech JobSearch**, operated by Arbetsförmedlingen (Swedish Public
Employment Service), after checking these official sources on 2026-09-17:

- [Open-data access policy](https://arbetsformedlingen.se/other-languages/english-engelska/about-the-website/apis-and-open-data):
  open data and open APIs are free for anyone to use, including building digital services.
- [JobSearch API](https://jobsearch.api.jobtechdev.se/) and
  [its Swagger contract](https://jobsearch.api.jobtechdev.se/swagger.json), version
  **1.37.0**: job ads are licensed under
  [CC0](https://creativecommons.org/publicdomain/zero/1.0/). This permits the
  intended display, reviewed copy and private editing of listings. The contract
  declares no API authentication requirement. No account, key or subscription is
  needed for this adapter.
- [Official getting-started guide](https://gitlab.com/arbetsformedlingen/job-ads/jobsearch-apis/-/blob/main/docs/GettingStartedJobSearchEN.md)
  is linked by the current Swagger contract.

The contract, rather than a third-party API directory, was used for endpoint,
parameter and field selection. Only documentation was fetched during development;
no live listing results were fetched or represented as verified. Test listings are
explicitly labeled synthetic. No Google/LinkedIn scraping or alternate-provider
fallback exists. Coverage is primarily Swedish advertisements, often in Swedish.

## Delivered flow and contract

`/discover` is linked in the authenticated navigation. Search -> preview ->
explicit import -> saved job is connected to the real application API/persistence.

| JobPilot control | Documented JobTech request |
| --- | --- |
| Keywords (up to 200 characters) | `GET /search?q=...` |
| Relevance / newest published | `sort=relevance` / `sort=pubdate-desc` |
| Likely remote | `remote=true`, omitted when unchecked |
| Previous / next | `limit=20`, bounded `offset`, `resdet=full` |
| Preview | `GET /ad/{id}` |

Remote is a **phrase-matching heuristic**, not confirmation of an employment
arrangement. Missing location, salary, workplace model, publication date or
deadline is shown as not supplied. Salary descriptions and workplace-model labels
are displayed as source text, without inventing numeric salary or remote status.
Dates preserve the source's offset (or absence of one); no timezone is inferred.
Exact-location and salary filtering are not offered in this milestone. Pagination
stops at 2,000 matches and asks users to refine large searches.

Results include title, employer, canonical Platsbanken link and available dates.
The adapter prefers `description.text`; HTML-only descriptions remain missing.
No provider HTML is inserted into the DOM. Search, preview and saved descriptions
render as escaped React text. Loading, empty, disabled/unavailable, rate-limit,
invalid-source and invalid/expired-preview states are surfaced without raw errors.

API routes require bearer authentication:

- `GET /api/discovery?q=&remote=false&sort=relevance&offset=0`
- `GET /api/discovery/{external_id}/preview`
- `POST /api/discovery/import` with `{preview_token, confirm: true}`

The normalized `external_id` is JobTech's primary ad `id`, not a guessed employer
identity or URL. Duplicate matching uses `(owner_id, source_provider,
source_external_id)` including archived rows, enforced by a unique database index.
Search/preview exposes only the current owner's existing job link. Duplicate
imports return that row without changing any edits or archiving state. Concurrent
insert conflicts are resolved using the same identity. Manually saved jobs without
source identity are not automatically deduplicated by URL or title.

Preview returns a signed, owner-bound, purpose-specific, 15-minute snapshot token
and `Cache-Control: no-store`. Import verifies it and persists exactly the previewed
data; it does not refetch or accept replacement source fields from the client.
Removed ads are rejected when previewing. A source can change or disappear after
preview; saving a reviewed snapshot is not a guarantee that the vacancy is open.

The provider adapter handles I/O and parsing only. Persistence is in a separate
service. Additive migration `a2b3c4d5e6f7` adds nullable source identity, normalized
source snapshot and import timestamp columns. Existing/manual rows retain null
provenance. Read-only provenance is visible on the saved-job page and survives
ordinary edits. Imported rows are ordinary saved jobs: fit analysis, reviewed pack
generation, export and tracking continue through their existing paths and gates.

## Bounds and setup

Fixed HTTPS host `jobsearch.api.jobtechdev.se`; only `/search` and bounded ad-ID
paths can be fetched. Provider-supplied URLs, logos and pagination links are never
followed. HTTP redirects are disabled. Requests use an eight-second HTTP timeout,
a two-megabyte decoded-response limit, zero retries and no fallback. Required
fields and saved-job length limits are checked; invalid/oversized results fail
visibly rather than silently losing job facts. Provider errors are mapped to safe
messages; unrestricted bodies are not logged or returned.

Defaults in `.env.example`:

```dotenv
JOBPILOT_DISCOVERY_ENABLED="true"
JOBPILOT_DISCOVERY_TEST_PROVIDER="false"
```

No discovery credentials are required. Discovery is independent of AI enablement
and changes no AI settings. Search keywords are sent to JobTech only on search;
profile facts and CVs are never sent to the discovery source. No background sync,
automatic import, automatic approval or application sending is introduced.

From `backend`, apply the additive schema update on another environment with:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
```

Local development was upgraded from `9c0d1e2f3a4b` to `a2b3c4d5e6f7`; user and
saved-job row counts were checked unchanged. Private `.env` was not edited.
The browser harness enables the synthetic discovery provider only with both
`E2E_TEST_MODE=true` and `POSTGRES_DB=POSTGRES_TEST_DB`. Production rejects that
provider outside those guards. Test mode is never a fallback for network failure.

## Verification and limitation record

Provider tests use `httpx.MockTransport`, with ordinary HTTP transport blocked.
They cover documented parameters, plain-text parsing, missing values, unsafe
source URLs, invalid and oversized data, timeout, rate limit, unavailable service,
redirect rejection, removed ads and mismatched IDs. Database/API tests cover
authentication, owner isolation, signed-preview integrity/expiry, required explicit
confirmation, read-only provenance, duplicate and archived imports, preserved
user edits, the uniqueness constraint and safe error responses.

Frontend component tests cover explicit search/preview/import, loading/empty/error
states, duplicate links, unknown values and HTML escaping. The connected browser
scenario verifies import, owner-visible saved provenance, editing, repeat-search
duplicate links, deterministic fit analysis and persisted application tracking.
The pack browser scenario also runs on an imported job, including confirmed CV,
generation, review/edit, explicit approval and PDF/DOCX exports. These checks use
synthetic providers and do not establish live source or AI reliability.

**Verification incident:** the first regression selection included the existing
`test_saved_jobs_migration` test, which internally downgraded and re-upgraded the
guarded test schema. The initial preservation flag only prevented fixture-level
truncation and did not prevent that downgrade. This breached the requested no-reset
constraint and could remove pre-existing saved-job/dependent test records; the
prior contents of that test database were not retained, so exact loss is unknown.
No recovery was attempted. Development data was not affected by that test.
Preservation mode now also skips legacy downgrade modules. New migration checks
inspect the upgraded schema without a downgrade. This incident is not described
as a wholly non-destructive verification run.

For preserved-data regression runs, set `JOBPILOT_TEST_PRESERVE_DB=1` only in the
test process. This skips truncation and downgrade tests; each ordinary database
test rolls back its own transaction. The browser harness cleans up only the
synthetic users it creates. Do not run the legacy migration tests when preserving
an existing database.

Final affected backend run: **120 passed, 1 skipped** (the legacy downgrade test),
with 14 existing Starlette/deprecated-status warnings. Frontend: **30 component
tests passed**; TypeScript and affected-file ESLint checks passed. Browser: discovery/import/fit/
tracking passed, as did both manual and imported pack approval/export scenarios
(three scenarios total). Desktop and 390-pixel mobile discovery screenshots were
inspected; the mobile page has no horizontal overflow. Existing Windows Watchpack
and Node color warnings did not block the browser run.

Retained screenshots: [desktop](../evidence/job-discovery-desktop-20260917.png)
and [mobile](../evidence/job-discovery-mobile-20260917.png), showing synthetic data.

Verification commands from the repository root:

```powershell
$env:JOBPILOT_TEST_PRESERVE_DB='1'
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_discovery.py backend/tests/test_jobs.py backend/tests/test_job_fit.py backend/tests/test_pack_configuration.py backend/tests/test_pack_provider.py backend/tests/test_pack_structural_labels.py backend/tests/test_pack_export.py backend/tests/test_application_tracking.py backend/tests/test_config.py backend/tests/test_saved_jobs_migration.py -o addopts= -q
# From frontend:
npm test -- --run
npx tsc --noEmit
npx playwright test tests/e2e/discovery.spec.ts tests/e2e/application-packs.spec.ts
```

No paid services, live AI requests, application sending, push, deployment or Jira
operations were performed. Unrelated checkout files and retained AI reports were
left unchanged.
