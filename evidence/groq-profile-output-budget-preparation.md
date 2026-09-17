# Profile output-budget failure: offline regression and proposed request

No live calls were made. This follows the retained production-profile report
storage/ai-evaluation/groq-profile-production-live-20260917-071751Z.json, whose
bounded provider explanation reports completion-token exhaustion, truncation,
and missing required root properties partial and message. Its failed generation
contains headline, location and skills, but no experience or education. Actual
usage remains unknown; a token-limit explanation is not a usage measurement.

## Validation defect fixed

The earlier diagnostic parsed the failed generation using defaults for partial
and message. It correctly retained HTTP failure as the overall result, but its
separate local-parse check misleadingly passed. GroqProfileOutput now requires
both root fields explicitly and recursively rejects omitted nested wire-required
fields, including nullable fields such as experience.period and notes. Domain
CandidateProfile models and their ordinary optional fields remain unchanged.

Regression fixtures reconstruct the retained three suggestions with synthetic
IDs and omit partial/message. Both the actual SDK mocked HTTP 200/completed path
and the HTTP 400 failed_generation path now produce missing-field errors and
cannot report contract_pass. Diagnostic-only failed-generation checks do not
accept or apply suggestions. The same stricter Groq model is used by the actual
profile adapter and the diagnostic. Evidence parsing and source-quote validation
remain mandatory. No defaults or synthesized quotes repair a failed output.

## Supported reasoning control and capability scope

Groq's [Responses API reasoning example](https://console.groq.com/docs/responses-api#reasoning)
explicitly uses openai/gpt-oss-20b and reasoning={"effort":"low"} on /responses.
That exact nested Responses parameter is used; the Chat Completions parameter
reasoning_effort is not sent. Only Groq profile extraction on that exact model
gets this setting. Fit analysis, application packs and OpenAI profile requests
retain their existing behavior, confirmed by mocked request tests.

The 2,250-token cap applies to the Groq profile-only pilot evaluation, selected
by --provider groq --pilot --task profile or the fixed profile_diagnostic entrypoint.
Other evaluation capabilities and application-wide token configuration are not
changed. Actual reasoning savings and full-profile completion are unverified.

## Redundant schema overhead removed

The six identical evidence-array schemas now share one $defs entry. Definition
names are shortened only on the Groq wire, with every reference updated. Expanding
all references gives exactly the same strict JSON schema as the previous request:
required keys, typed per-field values, nullable fields, literals/enums, closed
objects, evidence list bounds (1?10) and quote lengths (1?1,000) are preserved.
A regression compares those expanded schemas, and another prevents merging
arrays with different constraints. No new constraint was removed. Pre-existing
local-only ID/count/string constraints remain unchanged and still parse locally.

The production prompt and complete strong synthetic source are byte-for-byte
unchanged. The byte estimator and its 2,048-token allowance are unchanged.
The final serialization shrinks by 548 bytes, including the added reasoning
setting and changed format name. Required wire fields are now also checked
locally instead of silently supplied by defaults.

## Current versus proposed reservation

| Component | Previous profile evaluation | Proposed profile-only evaluation |
| --- | ---: | ---: |
| Serialized request bytes | 4,243 | 3,695 |
| Protocol allowance | 2,048 | 2,048 |
| Estimated input tokens | 6,291 | 5,743 |
| Maximum completion tokens, including reasoning | 1,500 | 2,250 |
| Total reserved tokens | 7,791 | 7,993 |
| Headroom under 8,000 TPM | 209 | 7 |
| Reasoning request | Omitted | effort=low |
| Exact estimated cost, USD | 0.000921825 | 0.001105725 |
| Upward-rounded budget, USD | 0.000922 | 0.001106 |

Rates are the existing planner assumptions ($0.075/M input, $0.30/M output), not
verified account billing. The completion allowance increases 50%. A 2,400-token
candidate would reserve 8,143 tokens and was rejected offline; the final cap is
2,250. No facts, required fields, validation bounds, estimator allowance or
other capability's token cap were reduced to fit.

Saved one-request profile-only dry run: groq-profile-lower-reasoning-dry.json.
It contains the actual serialized request representation and records zero sent.
Request SHA-256:
05544f6228fa6f619a53e2d0ef882507b209bd554b42a67e33dbe557df33534f.

The existing diagnostic live gate requires a matching fresh dry plan and the
new exact budget; old $0.000922 authorizations/reports cannot execute this plan.
Zero retries, the one-request transport guard, no fallback, bounded redaction
and production logging protections remain intact. A future live attempt needs
separate authorization and is not part of this task.

## Tests and limits

167 affected offline tests passed with five database tests excluded. After adding
the constraint-sharing guard, all 17 diagnostic tests passed (168 distinct affected
tests in total). Coverage includes HTTP failure and HTTP-success truncation,
nested required fields, schema equivalence, evidence bounds and source checks,
reasoning parameter scope, preserved other capabilities, budget gates and safe
capture. Sockets are blocked and responses mocked. git diff --check passed.

This prepares a sound bounded request; it does not prove 2,250 tokens plus lower
reasoning will produce a complete profile. Any future response still requires
factual/completeness review, and accepted suggestions require explicit user action.
Historical evidence and unrelated work were preserved. No reset, push, deployment
or Jira changes were made.
