# Apply form database verification

This earlier regeneration-based fix is superseded by
[the combined review-and-save implementation](../profile-review-save/README.md).

Verified 2026-09-24.

## Reported missing values

A read-only transaction against the configured application database found one
suggestion set, still `ready`, with no `applied_at` or `apply_result`. Its six
offered cards were two education entries, two languages, location, and skills.
All six pass the current evidence validator, including Arabic/native.

The set records `profile_revision="none"`, but a candidate profile was created
after generation. The confirmed source text and review timestamp still match.
Applying this set therefore returns HTTP 409 before saving any suggestions.
The manual fields were saved separately; the AI suggestions were never applied.
No application records were modified during this inspection.

## Fix

- Ready suggestions now offer an explicit **Regenerate suggestions** action.
- A profile save or Apply conflict marks the set outdated and disables Apply.
- Failed regeneration preserves edits, checked items, and the outdated state.
- Successful Apply and reopening the panel display the values actually saved in
  `apply_result`, including edits and the subset of items accepted.
- Backend conflict checks and explicit user selection remain in force.

## Database coverage

The local PostgreSQL `jobpilot_test` database was used for write tests, with
transaction rollback. No migrations, resets, or application-profile writes ran.
The configured remote server does not have `jobpilot_test`, so test processes
used existing local database credentials without editing `.env`.

All ten fields were compared with direct PostgreSQL column reads, the Apply
response, and a subsequent profile GET: headline, location, target roles, skills,
experience, education, languages, remote preference, work authorization, and
salary preference. Nested education/experience values and Arabic/native were
checked explicitly.

Cases cover an empty profile, an existing profile, creating a profile after
generation, and editing a profile after generation. They verify rejection without
partial changes, explicit regeneration and retry, preservation of existing list
entries, skill deduplication, edited values, persisted Apply history, and
idempotent repeat requests. Tests model separate-request timestamps explicitly
because the rollback fixture keeps PostgreSQL `now()` constant within its outer
transaction.

## Results

- Backend profile suggestions and candidate profile suites: **156 passed**.
- Frontend resumes, profile, and profile suggestion API suites: **45 passed**.
- TypeScript check and ESLint for changed frontend files: **passed**.
- Frontend tests exercise the form with mocked API responses; backend tests
  exercise real PostgreSQL. No live AI generation or browser E2E run was used.

The user's existing suggestion set still needs **Regenerate suggestions**, review,
and **Apply selected AI suggestions** after these frontend changes are loaded.
