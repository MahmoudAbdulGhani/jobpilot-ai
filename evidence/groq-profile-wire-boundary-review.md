# Provider wire boundary review (2026-09-17)

Reviewed ed05a0f offline. No live provider calls were made.

The commit's `AliasChoices("title", "job_title")` changed ordinary profile
validation: it accepted job_title in CandidateProfile inputs as well as provider
output. The fix restores app/schemas/profile.py exactly to ed05a0f's parent.
CandidateProfileUpdate, CandidateProfileResponse, and public apply selections
use title and reject job_title.

ProviderExperienceEntry instead declares required job_title and organization,
with the same title/organization/period/notes bounds. The SDK parses
ProviderWireSuggestionOutput, then an explicit to_domain conversion constructs
ExperienceEntry(title=job_title). Stored suggestions and public responses retain
title. Evidence bounds and source-quote validation remain enforced. Compaction
no longer renames any properties; existing local-only constraints remain local.

The rename is an **unverified compatibility workaround**. Retained report
storage/ai-evaluation/groq-profile-live-20260916-181746.json records BadRequestError
and HTTP 400, with unknown provider status and null usage. It retains no provider
error body identifying title as the cause. Earlier missing-title diagnostics do
not establish the cause of this later HTTP 400. No claim of provider success or
keyword collision is justified by these records.

## Final serialized request estimate

The planner now captures request.content through the real SDK and an httpx
MockTransport, including strict-schema conversion and the evaluation meter's
service_tier=default. It uses synthetic credentials and never opens a socket.
The independent serialization test compares the actual bytes' hash and estimate.

New report: groq-profile-wire-boundary-dry-run.json (historical reports preserved).
Canonical strong case, Groq profile-only pilot, OpenAI SDK 2.54.0/Pydantic 2.13.4:

- Serialized request: 4,212 UTF-8 bytes.
- Conservative input estimate: 4,212 + 2,048 = **6,260 tokens**.
- Maximum output: **1,500 tokens**; complete estimate: **7,760 tokens**.
- Configured reservation rates: $0.075/M input and $0.30/M output.
- Exact arithmetic estimate: **$0.0009195**.
- Planner's six-decimal rounded max_estimated_cost_usd: **$0.000919**.
- Request SHA-256: 31fa89cf50a1115b6850a69e7289b93d1ac8178bf82dc26e85d39a25410520de.

This is an offline estimate using existing configured rate assumptions, not
measured usage or verified account pricing. The former $0.00093 estimate was not
held fixed.

## Validation

Focused SDK, provider, evaluation, and profile-schema tests pass with blocked
sockets or synthetic mocked clients. They cover job_title-to-title mapping,
required SDK properties, unchanged public input/output rejection and bounds,
evidence validation, and final serialized request estimation. Five database
integration tests were excluded; no database or live-provider validation is
claimed. The public profile schema source was also compared directly with
ed05a0f's parent and is identical.
