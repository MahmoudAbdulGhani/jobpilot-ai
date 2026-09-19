# AI advisory capabilities (deterministic, no live provider calls)

JobPilot ships eight advisory capabilities over the customer's own saved data.
They are **deterministic local computations**: no AI provider is called, no
background jobs run, and nothing is sent anywhere. Each action is explicit,
each output cites its evidence, and every route is owner-scoped (cross-owner
access returns 404, indistinguishable from missing).

## 1. Cross-job ranking (`/api/rankings`, Saved jobs page)

Ranks owned, non-archived saved jobs against saved profile facts: skill/keyword
overlap (40), explicit required-term coverage (20), location (15), remote
preference (15: `office`/`hybrid`/`remote`) and seniority wording vs saved
experience entries (15). Returns score 0–100, reasons with verbatim job quotes
and profile facts, missing skills, risks and a recommended action. Runs are
persisted with profile/job hashes; reads report `is_stale` when inputs change.
Paginated run list; per-run items paginated. `POST /api/rankings {job_ids?,
include_archived?}` (max 100 jobs), `GET /api/rankings`, `GET
/api/rankings/{id}`, `DELETE /api/rankings/{id}`.

## 2. ATS/readiness report (`/api/jobs/{job}/packs/{pack}/ats-reports`, job detail)

Six explicit checks over an **approved** pack version vs its job: keyword
coverage, contact fields (email/phone patterns), date consistency (ranges
ending before they start), duplicate skills, unsupported claims (factual blocks
without evidence), evidence gaps (explicit job requirements unaddressed in the
pack). Readiness = mean of pass 1 / warn 0.5 / fail 0, versioned `ats-v1`.
Unapproved versions return 409. Existing pack/job validation is untouched.

## 3. Reply classification (`/api/replies/{id}/classification`, reply timeline)

Deterministic keyword classification of known reply previews: `interview`,
`rejection`, `information_request`, `offer`, `other`, with confidence (40–92),
verbatim evidence excerpt and uncertainty notes (including competing signals).
Classification never changes status. `POST .../confirm {confirm: true, status}`
applies a user-chosen status to the linked application (409 without a linked
application record or prior classification; 422 without explicit confirmation).

## 4. Follow-up suggestions (`/api/followup-suggestions`, Reminders page)

Generates reminder suggestions from application age (Applied/Interview, no
active reminder) and follow-up message drafts when a reply was received.
Persisted with `suggested/approved/rejected` state; generation is idempotent
while a suggestion is open. Approving a reminder creates it through the same
guards as the reminder controls (future time, terminal-status confirmation);
approving a draft only marks it for the user to copy — JobPilot never sends it.

## 5. Unified insights (`GET /api/insights`, Insights page)

Read-only aggregate: fit gaps with job links, applications by status with
origin, replies (200-char excerpts, senders reduced to `***@domain`), active
reminders with overdue counts, interview sessions. Owner-scoped; no persistence.

## 6. Privacy controls (`/api/privacy/matrix`, Settings page)

Server-backed data-use matrix per domain: fields used, purpose, provider,
retention, consent state. Optional AI uses (`ai_profile_suggestions`,
`ai_job_fit`, `ai_application_packs`) default to denied (least privilege) and
toggle with explicit confirmation; core storage rows are required; mailbox data
follows the connection in Settings. Advisory features are local-only.

## 7. Read-only Q&A (`GET /api/qa/ask?entity=&q=&limit=`, Insights page)

Keyword search over an explicit per-entity field allowlist (`jobs`,
`applications`, `reminders`, `replies`, `interviews`, `profile`, `packs`),
row limit 1–20 (default 10), every match cited with entity/id/field/excerpt/link.
GET and SELECT only — answering cannot write, send, change status or delete.

## 8. Daily digest (`/api/digest/*`, Discover page)

Cadence preferences (`off` default, `daily`, `weekly`) with explicit
confirmation. Previews use only cache payloads validating against the
DiscoveryJob contract (JobTech/Jobicy); invalid payloads are counted as
skipped, never repaired. Items carry source attribution, timestamps and the
synthetic-data marker. Delivery is structurally disabled: no delivery provider
exists, so digests are in-app previews only.

## Application record origin

Manual records are marked `manual`; records created by Gmail dispatch or reply
synchronization are marked `email_confirmed` (migration
`0ad80ddc2a00`). The API rejects client-set origins (422). The UI states
plainly that no email was sent for manual records.

## Verification and limits

Each capability has backend contract tests, component tests, and (for ranking,
suggestions, insights, Q&A, privacy, digest) browser coverage in
`tests/e2e/ai-advisory.spec.ts`. ATS-approval and reply-classification browser
journeys are covered by backend + component tests; the full guarded Playwright
suite must stay green. Deterministic tests validate the application contract,
not live-model quality. No live provider calls are made anywhere in these
flows; enabling the AI provider configuration does not change these engines.
