# AI workflow pilot acceptance — 2026-09-25

## Deployment and offline verification

- Commit `0b9042e` deployed to the tracked Render and Vercel services. The
  Vercel `/api/ready` endpoint returned 200 after the additive migrations.
- Disposable PostgreSQL backend suite: 1,074 passed, 5 skipped. Frontend unit
  suite: 136 passed. Frontend typecheck, lint and production build passed.
  Guarded browser journeys for AI advisory, packs, profile review and text/voice
  interview passed after correcting two stale test expectations. All development
  provider transports were mocked or blocked.
- Realtime voice remained disabled; no live voice request was part of this pilot.

## Controlled production profile request

- The operator explicitly chose their existing account and reviewed CV for this
  run instead of the originally planned separate synthetic account. The CV text,
  account identifier and credentials are intentionally omitted here.
- The operator confirmed the CV extraction and `ai_profile_suggestions` consent.
  Render was configured for the production-only pilot gate, the dedicated
  account UUID, OpenAI and `gpt-5-mini`, with test providers and live voice off.
- The operator reports one Generate click. The profile suggestion set reached
  **ready**, then **applied** after review. The supplied evidence quote contained
  the named skills **TypeScript** and **JavaScript**; the operator reports both
  now appear in the saved profile.
- The production gate atomically consumes a singleton dispatch claim before
  transport and suppresses the profile experience follow-up. This enforces at
  most one pilot dispatch across clicks and restarts. The production database
  claim and OpenAI provider logs were not independently inspected, so the
  exact provider-side dispatch count is not asserted from telemetry.
- The operator reports `JOBPILOT_AI_ENABLED=false` and
  `JOBPILOT_AI_PILOT_ENABLED=false` after the attempt. The deployed readiness
  endpoint returned 200 with the flags restored.
- Settings → Usage showed **47 consumed profile requests** for this admin
  account at the end, with an admin remaining allowance of 999999. No pre-pilot
  per-feature baseline was captured, so that aggregate cannot isolate this
  request. The disabled-provider label shown after the flag was switched off
  is expected.

No unrestricted provider response, CV text, account identifier or API key is
stored in this record. A second live profile request requires new authorization;
the durable claim must not be reset as a retry.
