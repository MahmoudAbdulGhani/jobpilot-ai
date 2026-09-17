# Text interview practice

Optional recording, reviewed transcription and spoken questions are now described
in [Voice interview practice](voice-interview-practice.md). The complete text
workflow and all content evidence checks remain unchanged.

From a saved job, choose **Prepare interview practice**. Select either a reviewed
CV or an approved application-pack version for that job, select behavioral,
technical or mixed practice, and choose 2–6 questions. Review the provider/model
and the source information, then explicitly confirm. Creating the private session
does not call AI; **Ask first question** starts the first request.

For a reviewed CV, the snapshot includes its confirmed text, the current saved
candidate profile (if present), and the saved job title/company/description. For
an approved pack, it includes the selected version's CV and cover-letter text,
the pack's original profile snapshot, and the current job. Current profile edits
are not substituted into a selected pack. Source ownership and reviewed/approved
status are checked server-side. A preview hash rejects changes between preview
and confirmation. Subsequent source edits never change the session snapshot.

The user answers one question at a time. **Save answer without AI** persists a
draft; **Submit answer and continue** saves first, then requests feedback and the
next question. Reload resumes the saved question and answer. Unsaved text remains
only in component memory, not browser storage. The final answer requests feedback
without another question. The final review collects every question, answer,
assessment, exact answer excerpt and actionable practice priority.

## Grounding and quality boundary

The model selects one of five bounded question strategies and an exact source
excerpt. Job questions cite the captured description; follow-up strategies cite
the latest answer. Mixed practice alternates behavioral and technical questions.
Repeated strategy/excerpt pairs, unknown strategies, unsupported excerpts and
missing required fields are rejected. The app renders the question wording
deterministically, including explicit hypothetical/unknown-experience language.

Feedback covers relevance, clarity, specificity and demonstrated technical
knowledge, with `demonstrated`, `needs_detail` or `insufficient_evidence` assessments.
Non-insufficient assessments require exact contiguous excerpts from that answer,
not the CV or job. Insufficient evidence has no supporting quote. Each dimension
also requires an allowed practice focus, such as contribution, concrete outcome,
mechanism, trade-offs or validation. Deterministic guidance turns that focus into
an actionable next step. Arbitrary feedback prose/candidate claims are not part of
the wire contract. Example answer **structures** are explicitly not claims about
the candidate. There are no hiring probabilities, external tools or code execution.

All job/document/answer content is explicitly untrusted in the provider prompt
and safely rendered as text. These checks reject fabricated/stitched quotations
and extra claim fields; they do not prove that an excerpt is relevant, that an
assessment is fair, or that technical statements in an answer are true. The UI
labels assessments as AI-generated guidance. The bounded strategy/rubric approach
is deliberately narrower than free-form interview coaching. Live question quality,
rubric calibration and pedagogical usefulness remain unverified. Optional voice
input/playback is documented separately and does not change this rubric.

## Configuration and limits

Only interview configuration is new; profile, job-fit and pack defaults remain
unchanged. `OpenAIInterviewProvider` reuses the existing OpenAI Responses client,
`ProviderFailure` boundary, server-side credential resolution and guarded test
gate. It uses strict SDK structured parsing, `store=false`, zero SDK retries and
no tools/fallback. Every response must be completed and locally validated.

| Setting | Default |
| --- | --- |
| `JOBPILOT_INTERVIEW_PROVIDER` | `openai` |
| `JOBPILOT_INTERVIEW_MODEL` | `gpt-5-mini` |
| `JOBPILOT_INTERVIEW_REASONING_EFFORT` | `minimal` |
| `JOBPILOT_INTERVIEW_MAX_OUTPUT_TOKENS` | `2000` |
| `JOBPILOT_INTERVIEW_TIMEOUT_SECONDS` | `60` |
| `JOBPILOT_INTERVIEW_MAX_INPUT_BYTES` | `32000` |
| `JOBPILOT_INTERVIEW_MAX_CALLS_PER_SESSION` | `10` |
| `JOBPILOT_INTERVIEW_MAX_SESSIONS_PER_USER` | `20` |

The existing `JOBPILOT_AI_ENABLED`, server-side `JOBPILOT_OPENAI_API_KEY`, and
`JOBPILOT_AI_MAX_REQUESTS_PER_USER` apply. The free default is 20 shared requests
per UTC calendar month, with one active allocation per user. Existing accounts
retain continuity access. See [plans and entitlements](plans-and-entitlements.md)
for feature ceilings and beta policy. Failed dispatches consume quota; deleting
sessions does not refund it.
A successful N-question session uses N+1 calls (3–7), not one call per session.
There are at most two explicit dispatches per step, also bounded by the session
and account allowances. No automatic retries occur, including on reload.

Snapshots are limited to 16,000 serialized UTF-8 bytes and each answer to 3,000
characters. The request bound includes instructions, schema and the full payload;
it is conservatively serialized before dispatch. Oversized material is rejected,
never silently truncated. The model receives the snapshot, prior questions and
their quoted excerpts, and only the latest full answer. The history shown to the
user still retains all saved answers. Session configuration is snapshotted; a
provider/model/prompt-version mismatch blocks further generation rather than
silently switching an ongoing session. Lowered input/call limits still apply.

Official references checked on 2026-09-17:

- [GPT-5 mini endpoint, structured-output support and pricing](https://developers.openai.com/api/docs/models/gpt-5-mini)
- [GPT-5 reasoning-effort options](https://developers.openai.com/api/docs/models/gpt-5)
- [Structured outputs and required fields](https://developers.openai.com/api/docs/guides/structured-outputs)

Minimal reasoning follows the setting already exercised by the application's pack
adapter and fits this constrained selection/rubric task; this is not a claim that
the new interview task has passed a live evaluation. New public settings are in
`.env.example`; no private `.env` value was modified or printed. Configure the
existing OpenAI key privately if absent. Interviews do not require Gmail access;
existing [Google setup blockers](mailbox-connections.md#google-setup-not-performed)
remain unchanged.

The final local presence-only check found an OpenAI key configured and
`JOBPILOT_AI_ENABLED=false`. Both were left unchanged. Normal interview model
requests therefore remain disabled locally until AI is deliberately enabled;
guarded browser tests use their separate synthetic configuration.

## Reliability, privacy and retention

The authenticated owner scopes every session, source, result and operation.
Session creation has a unique owner/request key; operation keys are unique within
a session. User/session row locks, revision checks and a committed dispatch claim
prevent repeated or concurrent submission from making duplicate model calls.
Reusing a key with a different request is rejected. The dispatch claim commits
before network I/O. Workers receive data only, never a database session.

A provider timeout, refusal, incomplete output or failed validation leaves the
answer saved and marks practice interrupted. Expired pending operations can be
resumed only by explicit user action. Failure outcomes are safe fixed categories;
raw provider errors, unrestricted bodies and credentials are not logged or stored.
Available successful-response token usage is retained; absent usage remains
unknown. A timeout may still have consumed provider resources. A late result
cannot overwrite a newer operation or recreate a deleted session.

Deleting a session removes its snapshots, answers, feedback and operation records.
Deleting the owning saved job or account cascades the same cleanup. Deleting a
CV, candidate profile or pack alone intentionally does **not** remove existing
interview snapshots. The user must delete the interview separately. There is no
automatic retention expiry in this milestone. Account-level content-free usage
counters survive session deletion. Logical database deletion does not assert
erasure from backups or upstream provider systems; `store=false` is not a promise
of zero provider retention. Deletion cannot cancel a request already dispatched.

## API and additive migration

- `GET /api/jobs/{job_id}/interviews/options`: metadata and up to 100 reviewed CVs /
  100 approved pack versions. No provider request.
- `POST /api/jobs/{job_id}/interviews/preview`: selected snapshot and confirmation
  hash. No provider request.
- `POST /api/jobs/{job_id}/interviews`: confirm/hash/key; create the private session.
- `GET /api/jobs/{job_id}/interviews`: owner-scoped stable UUID keyset pagination.
- `GET /api/interviews/{id}`: resume, saved source/answers/results and safe outcomes.
- `PATCH /api/interviews/{id}/answer`: save a revision-checked draft without AI.
- `POST /api/interviews/{id}/advance`: explicit, revision/key-checked model call.
- `DELETE /api/interviews/{id}`: delete owned session and children.

Additive migration **`f7a8b9c0d1e2`** follows `e6f7a8b9c0d1`, creating only
`interview_sessions`, `interview_operations`, their indexes and constraints.
It was applied to development and persistent test databases. All 19 pre-existing
tables had matching before/after row counts and whole-row fingerprints; the two
new tables started empty. After verification, all 21 tables again matched the
post-migration baseline in both databases. No reset, downgrade or truncation was
performed. Tests roll back isolated data or clean up only newly created synthetic
users. This is preservation evidence for this task, not a recovery claim about
earlier incidents.

## Offline verification

53 affected backend checks passed (22 interview cases plus existing pack adapter,
pack configuration and configuration checks). The final 22 interview tests also
passed after refining the synthetic plan. Six frontend tests, TypeScript and
targeted ESLint passed. The guarded browser scenario passed start → ask → answer
→ save → reload/resume → finish → review → delete. It uses the synthetic provider,
not a live AI service. No Google access, email or AI requests were made.

Coverage includes cross-user denial, CV/pack review requirements, immutable
snapshots, preview invalidation, saved answers, duplicate/concurrent submissions,
quotas, retry caps, expired requests, timeout/failure preservation, deleted-session
late results, exact evidence and unsupported feedback fields, actual SDK schema
and reasoning settings, HTTP rejection without retries, and deletion cleanup.
Destructive migration coverage was not run. Existing Starlette deprecation and
Windows Watchpack warnings remain.

From `backend`:

```powershell
$env:JOBPILOT_ALLOW_DESTRUCTIVE_TESTS='0'
.venv/Scripts/python.exe -m pytest tests/test_interviews.py tests/test_pack_provider.py tests/test_pack_configuration.py tests/test_config.py -o addopts= -q
```

From `frontend`:

```powershell
npx vitest run tests/interviews.test.tsx
npx tsc --noEmit
npx playwright test tests/e2e/interviews.spec.ts --workers=1
```

## Prepared synthetic evaluation — not executed

From `backend`, refresh the offline plan with:

```powershell
.venv/Scripts/python.exe -m app.evaluation.interview_plan
```

This module has **no live execution switch**. It uses the production request builder
and interview adapter with the SDK behind `httpx.MockTransport`. The prepared case
uses the strong synthetic CV/job, a supplied behavioral question, and an answer
that explicitly leaves the project's technology association unestablished. One
future request would assess that answer and select a technical follow-up.

| Reservation | Final prepared value |
| --- | --- |
| Planned live requests | 1 (0 sent) |
| Model / reasoning | OpenAI `gpt-5-mini` / `minimal` |
| Final serialized request | 5,117 bytes |
| Input reservation | 7,165 tokens (UTF-8 bytes + 2,048 allowance) |
| Completion cap | 2,000 tokens, including reasoning |
| Total reservation | 9,165 tokens |
| Calculated estimate | USD 0.00579125 |
| Ceiling rounded upward | **USD 0.005792** |

Pricing assumes standard uncached input at USD 0.25/M tokens and output at USD 2/M,
as documented on the model page. Byte-based reservations are conservative estimates,
not measured token usage; account billing and eventual actual cost are unknown.
Request SHA-256: `28554095d122e23d1899cae4a6601c66c3131c46023c6bb4e2717a2b40eaafac`.

Before any future live execution, obtain separate authorization, refresh the final
serialization/budget, and enforce a one-call counter with zero retries/fallback.
Record safe provider status, completeness, exact evidence checks and available
usage. Review assessment usefulness and question relevance separately from schema
validation, especially the unsupported Python/PostgreSQL-to-project association.
Stop after that call regardless of outcome. A successful diagnostic would not
establish general interview quality or full-session readiness.
