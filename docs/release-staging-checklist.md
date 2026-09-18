# Staging release — consolidated launch checklist

This checklist consolidates the current checkout (`feat/mailbox-connection-foundation`, HEAD `3c5dbbe`)
for a staging release. Legend:

- **Implemented** — code complete and exercised offline with guarded/synthetic providers.
- **Configured** — operator setting exists and is ready to receive a value.
- **Live-verified** — proven against a real external provider in the staging environment.
- **Blocked** — cannot be finished without operator credentials, domain decisions or purchase.

Nothing marked **Implemented** is, by itself, configured, deployed or live-verified.

## Release evidence (this checkout, non-destructive runs)

| Check | Result | Notes |
|---|---|---|
| Backend pytest | Passed | All checks green on the existing local Python env; 3 skipped test variants. |
| Alembic `heads` / `current` / `check` | No pending ops | Head and DB revision both `e2f3a4b5c6d7`; no upgrade operations detected. |
| Frontend typecheck (`tsc --noEmit`) | Passed | |
| Frontend lint (`eslint .`) | Passed | |
| Frontend vitest | Passed | 14 files, 86 tests. |
| Frontend production build (`next build`) | Passed | Required `JOBPILOT_DEPLOYMENT=production`, an HTTPS `JOBPILOT_BACKEND_ORIGIN`, and `NEXT_PUBLIC_API_URL=/api`; production guard works. |
| Playwright e2e (guarded providers) | Passed | 19/19 after two integration defects were fixed (see below). |

Two full-suite e2e failures were reproduced, diagnosed and fixed on this checkout:

1. **Discovery preview focus race** (`frontend/components/Discovery.tsx`): the heading was focused inside
   `requestAnimationFrame`, which can fire before React commits the `preview` state, so
   `previewHeading.current` is still `null` and focus is silently dropped. Focus now happens in a
   `useEffect([preview, saved])` run after commit. Both discovery scenarios previously failed
   intermittently under full-suite load; they now pass.
2. **E2E helper cleanup cascade** (`frontend/tests/e2e/helpers.ts`): `cleanupUser` failed on an email
   whose credentials had already been deleted, which aborts `afterEach` and leaves stale entries in the
   module-level `createdUsers` array that the next spec iterates. `cleanupUser` is now idempotent
   (returns quietly when the user was already cleaned). This surfaced as a spurious
   `application-pack` failure; the underlying pack workflow itself was sound.

## Connected journey — per feature

Each row states what was actually exercised with guarded/synthetic providers in the e2e run.

| Feature | Implemented (guarded evidence) | Configured | Live-verified |
|---|---|---|---|
| Accounts: invitation → verification → resumable onboarding → password reset | e2e green | `JOBPILOT_ACCOUNT_MAIL_TRANSPORT`, trusted app URL | Not until real SMTP is configured |
| Candidate profile editing | e2e green | n/a | n/a |
| Saved jobs CRUD + notes + own-profile editing | e2e green | n/a | n/a |
| Discovery: JobTech search, preview, reviewed import | e2e green | n/a | Real JobTech not exercised |
| Discovery: Jobicy remote cache, region filter, cross-source warning, explicit import | e2e green | n/a | Real Jobicy not exercised |
| AI profile suggestions | Workflow tested; wire contract verified | `JOBPILOT_AI_ENABLED`, key | Provider not live-tested |
| Fit analysis (explainable, becomes outdated) | e2e green | same AI settings | Not live-tested |
| Application packs: manual + imported, review, versions, approval, PDF/DOCX export | e2e green; exported bytes parsed and verified | n/a | n/a |
| Email applications: approved pack → guarded send → explicit reply sync, timeline, correction | e2e green | `JOBPILOT_ACCOUNT_MAIL_TRANSPORT`, Gmail send consent | Real send not made |
| Mailbox connection: naive + Gmail OAuth, incremental permission, revoke | e2e green (synthetic) | Google client, redirect URI, settings URL, encryption key | Real Gmail not connected |
| Interview practice: text + voice, transcripts, resume, review, delete | e2e green | voice/AI providers | Not live-tested |
| Resume library + ownership isolation | e2e green | private storage | Storage not live-tested |
| Usage display + exhausted actions preserve saved data | e2e green | plan limits policy | n/a |
| Reminders: create, reload, snooze, complete | e2e green | n/a | Closed-app reminders are not offered anywhere |
| Account data: private export, confirmed delete, disabled session, pending receipt | e2e green | cleanup scheduler, retention | Deletion not executed against persistent data |

## Entitlements and billing (audited, not changed)

- New/registered/invited accounts receive `free`; nothing can reach `legacy`/`invited_beta` over HTTP.
- Existing identities get `legacy` continuity by migration `e2f3a4b5c6d7` only; no expiry.
- Beta grants are CLI-only (admin allowlist, hours bounds, audit) and are not browser-reachable.
- Billing remains unavailable: no checkout, payment provider, active subscription or history exists.
  Paid plan numbers are inactive placeholders. No code change to grants was made for this release.

## Deployment configuration checklist

Backend (`deploy/production.env.example`, set on the backend only, never in the image):

| Variable | Value source / dependency | Mandatory at launch |
|---|---|---|
| `ENVIRONMENT=production`, `JOBPILOT_DEBUG=false` | static | required |
| `SECRET_KEY` | generated, random, ≥32 chars; do not reuse examples | required |
| `JOBPILOT_APP_URL`, `CORS_ORIGINS`, `ALLOWED_HOSTS` | single chosen browser origin; exact backend hosts | required |
| `AUTH_COOKIE_SECURE=true` | static | required |
| `JOBPILOT_PROXY_IPS` | real ingress proxy chain; empty rejects forwarded headers | required |
| `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | Supabase copy from dashboard | required |
| `POSTGRES_SSLMODE=verify-full`, `POSTGRES_SSLROOTCERT` | dashboard CA mounted | required |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | budgeted against pool ceiling `instances×workers×(pool+overflow)` | required |
| `JOBPILOT_STORAGE=supabase`, storage URL/bucket/key | private bucket + service-role key (server-only) | required |
| `JOBPILOT_REGISTRATION` | `invite-only` is the supported default | required |
| `JOBPILOT_ACCOUNT_MAIL_TRANSPORT`, SMTP host/from/user/password, `JOBPILOT_ACCOUNT_APP_URL` | SMTP for registration/recovery email | required before onboarding email works |
| `JOBPILOT_AI_ENABLED`, `JOBPILOT_OPENAI_API_KEY` | AI provider; disabled does not block startup | per-feature decision |
| `JOBPILOT_GOOGLE_CLIENT_ID/SECRET`, redirect URI, mailbox settings URL, `JOBPILOT_MAILBOX_ENCRYPTION_KEY` | Gmail OAuth, HTTPS redirects, restricted scopes | per-feature decision; key loss makes stored OAuth unusable |
| `JOBPILOT_PLAN_LIMITS`, `JOBPILOT_PLAN_ADMIN_EMAILS` | validated JSON policy; CLI admin allowlist | recommended |
| `E2E_TEST_MODE=false` and all `JOBPILOT_*_TEST_PROVIDER=false` | must stay false in production | required |

Frontend (`deploy/frontend.env.example`, frontend only; never backend secrets here):

| Variable | Value source / dependency | Mandatory |
|---|---|---|
| `JOBPILOT_DEPLOYMENT=production` | static | required |
| `JOBPILOT_BACKEND_ORIGIN` | HTTPS API origin (server-only); production build refuses non-HTTPS/invalid | required |
| `NEXT_PUBLIC_API_URL=/api` | same-origin rewrite on Vercel | required |

Release sequence (staging): build image → take verified DB + file backups → run one paid pre-deploy
command `python -m app.release` (serialized Alembic) → route traffic → run authorized post-deploy
checks per feature (login/refresh/logout, owner isolation, private storage round-trip, SMTP, each
optional integration separately). Full details in [deployment.md](deployment.md).

## Remaining launch blockers (priority order)

1. Domains, TLS original origin, and trusted proxy/client-IP chain; edge abuse controls before public registration.
2. Supabase: separate runtime/migration roles, Data API lockdown (`deploy/supabase-api-lockdown.sql`), CA mount, pool budget.
3. Private storage cutover: bucket/key, anon-denial proof, file manifest, copy/hash-verify, restore drill (no live storage calls made yet).
4. SMTP credentials + deliverability; then real account email.
5. Gmail OAuth publishing/verification + restricted scopes; do not request read scopes merely to send.
6. Real AI provider keys + separate spend/quality evaluation; synthetic history is not production verification.
7. Backups and restore drills executed: daily encrypted DB + object backups, 30-day retention, RPO/RTO decisions, deletion ledger, key-recovery test.
8. Production-signal checks (readiness `/api/ready`, health `/api/health`) verified behind the real proxy.

Nothing above was configured or live-verified during this task; all of it remains operator-owned.