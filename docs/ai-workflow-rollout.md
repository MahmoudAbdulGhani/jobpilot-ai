# AI workflow rollout and one-request profile pilot

The development `.env` keeps `JOBPILOT_AI_ENABLED=false`. Test-provider flags are
restricted to the isolated test database. The production pilot sends at most one
OpenAI profile request and does not enable live voice.

## Preflight

1. Deploy frontend and backend from the same verified commit. Apply migrations
   through `f9a0b1c2d3e4`; the `ai_pilot_dispatch` row must have `claimed_at=NULL`.
   Do not reset or edit the claim if a request fails or times out.
2. In the deployed app, create a dedicated account containing only the fixed
   synthetic CV below. Review and confirm its extracted text. Grant that account
   `ai_profile_suggestions` consent. Note its account UUID through an authorized
   administrative route or database query without logging credentials.
3. Set backend secrets through the deployment provider, never in a tracked file:
   `JOBPILOT_AI_ENABLED=true`, `JOBPILOT_AI_PROVIDER=openai`, the existing
   `JOBPILOT_AI_MODEL`, `JOBPILOT_OPENAI_API_KEY`,
   `JOBPILOT_AI_PILOT_ENABLED=true`, and
   `JOBPILOT_AI_PILOT_ACCOUNT_ID=<dedicated account UUID>`.
   Keep `JOBPILOT_LIVE_VOICE_ENABLED=false` and every test-provider flag false.
   Verify the deployed readiness endpoint and private account login before the
   request. The pilot gate rejects every other account and AI feature.

Upload [the fixed DOCX](fixtures/ai-pilot-synthetic-cv.docx). Its person,
employer and education are fictional. The reviewed extraction must include
each of the four skill lines before the request:

```text
Avery Test
Synthetic backend engineer

SKILLS
Python
PostgreSQL
FastAPI
Docker

PROFESSIONAL EXPERIENCE
Backend Engineer, Cedar Labs, January 2022 to December 2024
- Built REST APIs in Python and FastAPI.
- Designed PostgreSQL tables and queries.
- Packaged local services with Docker.

EDUCATION
BSc Computer Science, Example University, 2021
```

Expected review: each skill is a separate suggestion with an exact supporting
quote from this CV. Confirm only suggestions supported by the reviewed text.

## One request

From the dedicated account, request profile suggestions once. Poll the existing
suggestion status endpoint; do not click Generate again. The claim is committed
before HTTP dispatch and is never refunded. The profile experience follow-up is
disabled during the pilot. Review skills as individual list entries against the
synthetic CV and confirm only supported suggestions. Check the saved profile after
confirmation. Record the request status, model, safe failure category and available
usage, plus the profile result, without recording the key or unrestricted response.

If generation fails, is incomplete, or has no acceptable draft, stop. The one
request allowance has still been used. A further live call needs a separately
authorized pilot; do not clear the durable claim as a retry.

After the attempt, restore `JOBPILOT_AI_ENABLED=false` and
`JOBPILOT_AI_PILOT_ENABLED=false` in the production deployment settings and verify
other AI actions remain disabled. No digest email, voice session, pack generation,
job-fit call, Q&A call, or interview call is part of the pilot.

## Live voice boundary

`JOBPILOT_LIVE_VOICE_ENABLED=false` remains the production default. Its new
WebRTC token path uses a one-use interview-session claim and keeps audio out of
JobPilot storage. Captions stay in browser memory until the user confirms edited
question-and-answer turns; confirmed text is then stored and checked for feedback.
The browser's ten-minute timer is a UI limit, not a provider-side spending cap.
Do not enable this flag until realtime session billing, server-side termination,
device behavior, and privacy controls have a separate production review.
