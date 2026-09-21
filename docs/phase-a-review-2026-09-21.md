# Phase A review — 2026-09-21

Scope: consent, production Q&A, evidence validation, and reviewed digest delivery only. No commits, pushes, environment-file edits, live provider requests, new migration files, scheduled delivery, dashboard, or landing-page work.

## Inherited work and attribution

Initial branch: `feat/mailbox-connection-foundation`, tracking the same origin branch. HEAD: `a5ca2ab` (`testing uploading resume problems fixed`). Recent commits concern resume fixes and logging; the Phase A work was uncommitted. Attribution below comes from local tool edit records, not inferred Git authorship.

- Earlier Codex session `01a0c3c6-4cce-7de0-8572-3d896f0b6e40`: consent service and gates for profile/fit/packs/interviews/voice/Q&A; interview and voice privacy rows; initial evidence validator; removal of the production Q&A exclusion; explicit fallback configuration; hourly Jobicy catalog handling and signed digest review tokens; digest API/schema/UI changes; offline test-network fixture and runner.
- OpenCode session `ses_f3bf543b7ffeB9RU1o5jBvoA5p`: continued Q&A fallback ordering, added `consent_helpers.py`, updated consent setup and denial/revocation tests across profile, fit, packs, interviews, voice, entitlements and account deletion; rewrote digest tests for the catalog/token contract; updated Q&A, wire-schema and diagnostic tests.
- Five modified PNGs already existed at entry. Their authorship was not established; they were preserved untouched.
- No merge conflict markers or competing duplicate service implementations were found. Valid work from both tools was retained.

## Gaps repaired in this continuation

- ATS improvement now rechecks active ownership and stored pack consent after quota reservation and immediately before provider dispatch. Revocation returns 403, releases the reservation, and creates no improved version.
- Structured profile values were being converted using Pydantic's object representation, rejecting authentic experience/education/language evidence. Values now flatten from model fields. Experience and education must fit a single cited passage.
- Evidence checks reject unsupported terms/numbers, irrelevant citations, invented work verbs/durations and positive claims derived from explicitly negated evidence. Pack creation and ATS improvements retain the draft/explicit approval contract.
- Q&A now validates answer content as well as citation membership. Production-mode regression coverage uses a mock provider and proves owner-scoped retrieval, actual AI-branch dispatch, and rejection of fabricated claims/numbers/foreign citations. The deterministic Q&A provider emits source excerpts so it follows the same validator.
- Digest tests exercise the actual `JobicyCatalog.load()` output, including empty availability-check maps; stale/future refresh timestamps, expired deadlines, malformed deadlines and failed availability checks; expired, foreign, changed and replayed approvals. Synthetic listings retain their warning in the exact reviewed email body.
- Digest frontend tests now require a displayed preview and submit its exact approval token. The old tests still expected sending without a preview.
- Updated the privacy-matrix assertion for the new interview/voice consent rows.
- The inherited runner assigned the same database to development and test settings and used populated test data. Added fresh isolated local database mode, cleanup restricted to databases created by that invocation, and child-output credential redaction. Existing databases and environment files are preserved.

## Verification executed in this continuation

These are newly executed results, not historical Codex/OpenCode test claims. Counts are per invocation and overlap; do not sum them as unique tests.

| Run | Result |
| --- | --- |
| First attempted focused command | No tests executed: referenced nonexistent `test_application_packs.py`; command corrected |
| Initial seven-area focused run | 85 passed, 1 failed (structured evidence bug, subsequently fixed) |
| Initial full backend on inherited runner | 846 passed, 14 failed, 6 skipped |
| Evidence/consent/profile/Q&A focused run | 56 passed |
| Digest/Q&A/consent/evidence focused run | 63 passed |
| Final broad Phase A focused run, 14 test files | 259 passed |
| First isolated full backend run | 912 passed, 4 failed, 4 skipped |
| Pre-review isolated full backend run | 913 passed, 4 failed, 4 skipped |
| Consent-race and CLI focused run after review fixes | 101 passed |
| Final broad Phase A run after review fixes, including CLI | 282 passed |
| Final isolated full backend run after review fixes | 922 passed, 4 skipped |
| Frontend Vitest | 102 passed across 23 files |
| Frontend typecheck | Passed, including rerun after test edits |
| Frontend lint | Passed, zero warnings on final run |
| Alembic check against existing local test schema | Passed: `No new upgrade operations detected.` |
| Git diff whitespace check | Passed; Git emits existing LF/CRLF normalization notices |

Final focused command (from repository root):

```text
rtk proxy backend\.venv\Scripts\python.exe backend/tests/run_phase_a.py --isolated tests/test_cli.py tests/test_ats.py tests/test_profile_suggestions.py tests/test_job_fit.py tests/test_interviews.py tests/test_interview_voice.py tests/test_qa_ai.py tests/test_digest.py tests/test_privacy.py tests/test_evidence_validation.py tests/test_phase_a_consent.py tests/test_profile_wire_schema.py tests/test_pack_diagnostic.py tests/test_pack_structural_labels.py tests/test_pack_provider.py --tb=short
```

Full backend command: `rtk proxy backend\.venv\Scripts\python.exe backend/tests/run_phase_a.py --isolated --tb=short`.

Alembic command: `rtk proxy backend\.venv\Scripts\python.exe backend/tests/run_phase_a.py --alembic-check`.

Frontend commands (in `frontend`): `rtk proxy npm run typecheck`, `rtk proxy npm run lint`, `rtk proxy npm test`.

The pre-review 913/4/4 run failed in four `test_cli.py::TestResetPasswordCli` cases: `test_resets_password_and_invalidates_sessions`, `test_only_password_fields_change`, `test_unknown_email_refused`, and `test_inactive_user_refused`. The CLI and those tests predated Phase A, but the failures were exposed by the new isolated runner setting `ENVIRONMENT=test` while removing disposable-database authorization variables. The modified `conftest.py` offline socket/SMTP guard did not affect them. The behavior tests now provide an explicitly confirmed synthetic disposable URL and bind its engine factory to the per-test transaction; the CLI safety checks and their refusal tests remain enabled. That real disposable path also exposed a detached-instance read after its temporary session closed, fixed by copying the reset email before session exit. The final full backend run passes all four CLI tests. The four remaining skips require separately opted-in destructive migration testing. Browser E2E was not run. Vitest emits an existing non-failing jsdom navigation message; backend emits dependency deprecation warnings.

The final review also added race-window coverage for profile suggestions, job fit, application-pack generation, interviews and voice. If consent or account access changes after reservation/operation creation but before provider dispatch, each path now makes zero provider calls, releases the active reservation, persists a terminal failed/interrupted outcome, returns the same terminal result for the same idempotency key, and permits a fresh-key retry after consent is restored.

## Migration and production impact

No model/schema changes or new migration files. Existing migrations were applied only to newly created isolated local test databases, which the runner removes afterward. Alembic check found no drift in the existing local test database.

- Keep `JOBPILOT_QA_STRUCTURED_FALLBACK=false` (the new default) unless explicitly choosing labelled keyword fallback. Provider/configuration failures otherwise return a safe 503; missing/revoked AI consent returns 403.
- Production Q&A requires `JOBPILOT_AI_ENABLED=true` and existing valid AI provider/model/key configuration. No key or environment value was changed or tested live.
- Users must grant their own stored consent: `ai_profile_suggestions`, `ai_job_fit`, `ai_application_packs` (also ATS improvement), `ai_qa`, `ai_interview`, and `ai_voice`. Existing request-level speech consent remains required. No consent is backfilled or automatically granted.
- Voice still needs its existing enablement/provider settings. Test-provider flags and E2E mode must remain off in production.
- Digest mail stays disabled by default. If operators separately enable its existing SMTP configuration, sending still requires the exact reviewed recipient/content/catalog/transport snapshot and a token expiring after ten minutes. Catalog freshness is one hour; known expired/unavailable records are excluded. Deploy the digest frontend and backend together because the send API now requires `preview_token`. No scheduler is added.

## Remaining limits

All targeted Phase A regressions and the full non-destructive backend suite pass. Four destructive migration tests and browser E2E remain unexecuted. Live provider behavior was deliberately not exercised.

Evidence validation is conservative lexical checking, not a semantic truth proof; it can reject legitimate paraphrases and cannot establish the truth of user-supplied source material. Customer approval remains mandatory for documents. Consent revocation blocks subsequent dispatches; already dispatched external requests cannot be recalled. Digest freshness uses the existing hourly catalog and known availability results, without introducing live availability calls during preview/send.

## Files and final working tree

This continuation edited:

```text
backend/app/services/ai_provider.py
backend/app/services/application_pack_service.py
backend/app/services/digest_service.py
backend/app/services/evidence_validation.py
backend/app/services/privacy_service.py
backend/app/services/profile_suggestion_service.py
backend/app/services/qa_service.py
backend/tests/run_phase_a.py
backend/tests/test_ats.py
backend/tests/test_digest.py
backend/tests/test_privacy.py
backend/tests/test_qa_ai.py
frontend/tests/digest-panel.test.tsx
```

New files in this continuation: `backend/tests/test_evidence_validation.py`, `backend/tests/test_phase_a_consent.py`, and this report. The evidence validator and runner were already untracked at entry.

The final review-fix continuation additionally edited `backend/app/cli.py`, the five consent-gated services, `backend/tests/conftest.py`, `backend/tests/test_cli.py`, and the corresponding profile/fit/pack/interview/voice tests. All work remains uncommitted on the original branch.
