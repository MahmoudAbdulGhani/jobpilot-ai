# Plans and entitlement foundations

This milestone has **no checkout, payment collection, active subscriptions or
billing history**. USD 8/month is a configurable business hypothesis, not an
enabled subscription. No payment provider or merchant eligibility is assumed.
User accounts, data access, approval and document export remain independent of
AI availability and allowance. Existing AI/speech provider settings are unchanged.

## Access and configuration

`JOBPILOT_PLAN_LIMITS` is a validated JSON object with exactly `free`, `legacy`,
`invited_beta` and `paid`. Each accepts `total` and individual `profile`, `fit`,
`pack`, `interview`, `transcription`, `speech` limits (integers 0–10,000).
An omitted/null feature limit inherits the plan total, except continuity features
inherit `JOBPILOT_AI_MAX_REQUESTS_PER_USER`. Zero explicitly excludes a feature;
zero total blocks ordinary shared-budget requests. A new confirmed CV's first
profile generation can exceed the shared monthly cap if the plan still enables
the profile feature. Invalid policy fails configuration validation.

Default policy:

| Access | Shared monthly total | Per-feature ceiling | Assignment |
|---|---:|---:|---|
| Free | 20 | 20 each, sharing the same 20 | New users, including newly registered invitees |
| Existing-user continuity (`legacy`) | 60 | 20 each | Existing identities at migration; no expiry |
| Invited beta | 100 | 100 each, sharing the same 100 | Authenticated local administrator; 1–2,160 hours |
| Future paid | 200 (placeholder) | 200 (placeholder) | Inactive catalog only; cannot be assigned |

Free total defaults to `JOBPILOT_AI_MAX_REQUESTS_PER_USER` (20). Continuity total
defaults to three times that setting. The previous implementation had separate
profile/fit row-count limits plus a shared counter for packs/interviews/speech;
continuity starts with fresh monthly reservations and allowances covering those
three pools. No existing user is expired, moved to free, disabled or demoted by
migration `e2f3a4b5c6d7`. Their existing usage history is left intact. The initial
monthly balances are new allowances, not a claim that historical usage was zero.
Normal per-session interview/speech/input/output limits still apply.

Example policy (in backend secret/config management or untracked local `.env`):

```dotenv
JOBPILOT_PLAN_LIMITS='{"free":{"total":20,"pack":4,"transcription":4},"legacy":{},"invited_beta":{"total":100},"paid":{"total":200}}'
JOBPILOT_PLAN_ADMIN_EMAILS=
JOBPILOT_PROPOSED_MONTHLY_PRICE_USD=8.00
```

Limits apply immediately from server configuration. Changing them can reduce
future eligibility; do not silently lower continuity limits as part of a rollout.
Catalog entries are not provider spend guarantees. Paid numbers are placeholders
for later product decisions and grant no access. Database assignments allow only
free/continuity; beta has a separately bounded expiry. No request body, browser
flag, query parameter or unauthenticated CLI argument can assign paid access.

## Metering, periods and failures

Every feature uses `ai_usage.reserve(..., feature=...)` before provider dispatch.
There is **one authoritative monthly reservation ledger**, not six independent
mutable counters. An active user's row lock serializes allowance checks, ledger
inserts and the existing shared in-flight lease across processes. All commit
together before network I/O. Existing `AIUsage.requests` remains a cumulative
historical aggregate, updated in that same transaction; it is no longer the
lifetime eligibility gate. It is not displayed as monthly consumption. Historical
per-feature reservations cannot reliably be reconstructed from deletable results,
so no backfilled counts or billing claims are fabricated.

| Feature | One metered unit |
|---|---|
| Profile | One bounded suggestion-generation request |
| Fit | One bounded job-fit request |
| Pack | One request producing both CV and cover-letter drafts |
| Interview | One question/answer-assessment request, including the first question and final feedback |
| Transcription | One bounded recording request, up to the configured 60-second maximum |
| Spoken question | One bounded question/excerpt speech-generation request |

Regular accounts get one initial profile generation for each distinct confirmed
CV text and two additional profile refreshes per UTC month across all their CVs.
An initial generation bypasses the shared monthly ceiling but still creates a
usage reservation and remains visible in usage totals. A disabled profile feature
cannot use this exception. Configured plan administrators bypass generation
ceilings. The resume-specific eligibility endpoint reports the next request type,
remaining refreshes and reset date; the server rechecks under the account lock.
Profile review, saving and manual editing use no AI reservation.

`profile_generation_requests` stores only the account, a SHA-256 hash of the
confirmed text, request type and timestamps, independently of resume rows.
Deleting and reuploading the same text does not grant another initial request.
The ledger is included in account export and cascades on account deletion.
The migration backfills surviving suggestion sets as legacy source claims;
deleted historical CVs cannot be reconstructed.

All plans use **calendar months in UTC**, resetting on the first day at **00:00
UTC**. No reset worker edits counters. The current UTC bucket is selected at
reservation time after locking the user; prior rows remain history. No rollover
credits. All features share the total, so displayed feature balances are not
additive. Keep server clocks synchronized. Reload/Refresh usage shows current
period/expiry policy; an already-open tab can be stale, and the server always
rechecks before admitting a new reservation.

Only a durably committed reservation consumes allowance. Invalid inputs rejected
before reservation and rolled-back claims do not. Provider rejection, validation
failure, timeout, interrupted execution and unknown dispatch outcomes retain the
unit: the provider may have incurred usage. A crash between claim and network
dispatch is conservatively counted. No automatic refunds, retries or fallback.
Release ends the shared in-flight lease; it does not refund a unit or assert
provider success/billing. Existing idempotency controls return existing results
without new reservations. Deleting results/sessions does not restore allowance.

An already-admitted request may finish after beta expiry/revocation; new
reservations use the current plan. Expiry or revocation returns to the original
base plan (including continuity), not always free. Plan changes never reset the
current month's consumption. If usage already exceeds the base allowance,
additional requests are blocked until reset or an authorized larger grant.

## Administrative beta grants

There are no web administrator privileges or grant endpoints. A local operator
must explicitly list an **existing verified active account email** in
`JOBPILOT_PLAN_ADMIN_EMAILS`, then authenticate that account's password via
`getpass`. Merely knowing a target UUID or using the owner account is insufficient
without the allowlist. No passwords in command arguments, files or logs.
Authentication attempts are hash-key throttled (ten/hour per administrator email).
Access to deployment configuration/database credentials remains a privileged
operator responsibility; do not distribute it to ordinary users.

From `backend`, substitute actual account UUIDs and fresh UUID request keys:

```powershell
.\.venv\Scripts\python.exe -m app.cli beta-grant --admin-email <allowlisted-email> --user-id <target-uuid> --request-key <uuid> --reason invited_beta --hours 168
.\.venv\Scripts\python.exe -m app.cli beta-revoke --admin-email <allowlisted-email> --user-id <target-uuid> --request-key <different-uuid> --reason support
```

Allowed reason codes: `invited_beta`, `evaluation`, `support`; no unrestricted
note fields. Repeat the same key and parameters to retrieve the original audit
receipt without extending a grant. Reusing a key for different parameters fails.
Successful grant/revoke records include target, actor, action, reason code,
timestamp and expiry. Expiry derives from the audited deadline and needs no worker.
There is no invitation email or payment event. Settings shows the effective plan;
an old idempotent audit receipt is not proof that its grant is still active.

## Settings, privacy and deletion

Settings → **Plan and usage** shows the authenticated user's actual configured
allowance, reservations, remaining balance and reset timestamp. Provider-disabled,
not-in-plan, exhausted, loading and unavailable-usage states are distinct. Paid
action buttons fail closed while usage is unavailable and refresh after dispatch;
direct HTTP requests face the same server policy. Reviewing/editing existing
documents, approved PDF/DOCX exports, data export and account deletion are unmetered.

The additive migration creates only `account_plans`, `usage_reservations` and
`plan_audits` plus their indexes/constraints/inactive-owner write barriers.
It inserts continuity assignments for existing identities without rewriting any
old account or counter. All three tables are owner-scoped and cascade on account
cleanup. No raw prompts, audio, credentials or payment data enter this ledger.
Private account exports include plan metadata, reservation history and audit
decisions, excluding actor identity and internal request hashes/keys. If an actor
deletes their account, another user's grant/audit remains and its actor reference
is nulled. Administrator-email throttle records are removed by account cleanup;
other expired throttle records follow existing operational retention.

Plan assignments, reservation and grant history persist until account deletion.
They are not removed when a result is deleted or at monthly reset. This avoids
quota refill through deletion. Existing bounded-export limits and backup-retention
limitations still apply; deletion does not promise immediate erasure from backups.
No legal-compliance certification is implied.

## Future payment boundary — not implemented

Establish merchant eligibility, operating entity/country, commercial terms,
supported payouts/currencies, tax/refund obligations and provider costs before
selecting a payment provider. Do not assume a public API or advertised free tier
establishes merchant eligibility. This milestone makes no provider-specific claims.

Future work must use server-created customer/subscription mappings and verified
signed webhooks (raw payload verification, replay/timestamp checks, rotation).
Persist provider event IDs under unique constraints and process idempotently in
a transaction. Browser return URLs, checkout success screens and frontend plan
parameters must never grant paid entitlements. Define trial, active, past-due,
grace, cancellation-at-period-end, immediate cancellation, expiry, refund and
dispute policies before connecting lifecycle events to access. Handle duplicate
and out-of-order events with authoritative state/version checks. Bound and audit
reconciliation against the provider; report uncertainty without inventing payment
history. Cancellation must not delete user data or disable export/account deletion.
Keep subscription billing periods separate from the presently defined UTC calendar
allowance periods unless an explicit, reviewed migration changes that policy.

## Verification boundaries

Tests use mocked/deterministic providers and synthetic records only. They exercise
all six actual dispatch gates, owner isolation, the last-unit concurrency race,
UTC/leap-year/year boundaries, beta expiry/revocation, administrator authentication,
idempotent grants, rejected paid assignments, failed/unknown reservations, retained
quota after result deletion, exports/deletion and inactive-account write barriers.
The exhausted-usage browser fixture requires guarded E2E/test-provider settings,
the dedicated test database and a synthetic user created by that server process.
It creates bounded reservation fixtures, reports zero provider requests and refuses
existing accounts. Production cannot enable E2E/test providers.

No payment, live AI/speech/Google request, email, database reset/downgrade or
deployment is needed for these checks. Merchant/payment eligibility and real
billing lifecycle verification remain future blockers. Existing Google and speech
setup requirements are unchanged.

### Recorded offline checks

- Affected backend regression run: 147 passed; subsequent entitlement/account-data
  checks: 33 passed. The final entitlement module has 20 passing cases, including
  the added configuration-boundary regression (verified separately).
- Affected frontend component checks: 41 passed; TypeScript, targeted ESLint and
  the production frontend build passed.
- Five guarded browser scenarios passed: usage/exhaustion, manual and imported
  pack review/approval/PDF-DOCX export, text interview and voice interview.
- Only additive migration `e2f3a4b5c6d7` was applied locally. Read-only counts and
  row fingerprints matched the before-migration baseline for all 27 preexisting
  data tables in each development/test database. The schema-version table changed
  as expected; the existing development identity received one non-expiring
  continuity assignment. Synthetic reservation/audit rows were absent after
  cleanup. This verifies this task's data preservation, not backup restoration.
- No destructive migration coverage or live-provider verification was performed.
