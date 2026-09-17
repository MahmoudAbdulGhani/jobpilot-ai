# Groq profile integration: offline contract diagnosis

Reviewed from af9574a on 2026-09-17. No new model/API calls were made. Official
public documentation was read; all SDK executions used MockTransport and blocked
sockets. Unrelated working-tree files and historical reports were preserved.

## Confirmed documentation findings

Groq's [Responses guide](https://console.groq.com/docs/responses-api#using-a-schema-validation-library)
explicitly demonstrates OpenAI Python responses.parse with openai/gpt-oss-20b,
text_format=PydanticModel, and a real title property. Its structured-output
examples use text.format with type, name, and schema. The installed SDK adds
strict=true for that same parse interface. The exact endpoint/model/interface
is therefore documented; switching to Chat Completions is not justified merely
because Responses examples omit a literal strict flag.

Groq's [structured-output guide](https://console.groq.com/docs/structured-outputs)
lists GPT-OSS 20B for strict mode and requires every property in required plus
additionalProperties=false for every object. It documents anyOf, nullable values,
$defs and $ref, and demonstrates properties named title. It also describes
best-effort generated-JSON schema failures returning HTTP 400, separately from
strict-mode guarantees. No explicit definition of the literal json_validate_failed
code was found in the official pages searched. The guide does not explicitly
settle support for const or the length/count bounds present in our request;
absence of an entry is not proof those keywords are rejected.

The [API reference](https://console.groq.com/docs/api-reference) documents POST
https://api.groq.com/openai/v1/responses, text configuration, max_output_tokens,
store=false and service_tier=default. Groq's [error guide](https://console.groq.com/docs/errors)
provides generic HTTP categories and says the error message describes the issue;
it does not uniquely map HTTP 400 to the stage of schema validation.

## Retained evidence and diagnostic limits

storage/ai-evaluation/groq-profile-live-20260917-065543Z.json retains one attempt:
HTTP 400, BadRequestError, invalid_request_error, json_validate_failed,
provider_status=unknown, output=null and usage=null. It retains neither the
provider's error explanation nor failed_generation. A targeted search of the
retained evaluation/evidence files found no matching explanation or failed output
for this attempt. Those missing details cannot be reconstructed offline.

The report's http_rejection/bad_request tags describe the HTTP outcome only.
They do NOT establish rejection of the supplied schema before generation.
A request-schema rejection means the server refuses the schema/parameters;
a generated-output validation failure means output fails the requested contract.
A client parsing failure is a third stage, represented by sanitized Pydantic
locations after a response reaches the SDK parser. This run has no such client
validation locations. Successful parsing plus quote validation would instead
produce contract_pass and checks; neither occurred here.

Generated-output failure is a plausible hypothesis from the code's name and the
documented failure mode, not a proven explanation of this attempt. Invalid JSON,
missing fields, output truncation, endpoint implementation differences, and a
provider defect cannot be distinguished from the retained record. HTTP 400 does
not prove a title collision. The job_title rename remains unverified. Usage,
billing, generated content and the precise failing field remain unknown.

## Actual SDK serialization comparison

The current real SDK, pointed at an offline MockTransport, emitted
[groq-profile-request-offline-20260917.json](groq-profile-request-offline-20260917.json).
Only its synthetic request body was saved, never headers or credentials.
It is 4,212 bytes; SHA-256:
31fa89cf50a1115b6850a69e7289b93d1ac8178bf82dc26e85d39a25410520de.
This matches the last live report's planned request hash. The historical raw
network request itself was not retained; this is a reproducible serialization,
not a newly recovered network capture.

| Item | Observed request / finding |
| --- | --- |
| Endpoint/model | /openai/v1/responses; openai/gpt-oss-20b |
| Format | text.format.type=json_schema; strict=true |
| Envelope | store=false, service_tier=default, max_output_tokens=1500; no tools or streaming |
| Required fields | All properties required across all 11 objects; extras forbidden |
| Experience | job_title, organization, period, notes required; optional values nullable |
| References | All 15 references resolve to local $defs |
| Composition | anyOf; disjoint field literals encoded as const |
| Full keyword inventory | $defs, $ref, additionalProperties, anyOf, const, enum, items, maxItems, maxLength, minItems, minLength, properties, required, type |
| Demonstrated incompatibility | None identified against the documented requirements |

Some constraints omitted by wire compaction remain enforced locally, as before.
That can explain certain client parsing failures but does not establish the
cause of this server HTTP error. No schema constraints were relaxed during this
review. Domain mapping, evidence checks, explicit selection/review, zero retries,
and no fallback remain intact. OpenAI production behavior is unchanged.

## Decision, tests and smallest next live diagnostic

No provider-adapter replacement is justified by the available evidence. This
change commits the diagnosis, synthetic request artifacts and regression tests
only; it makes no production change. All 138 focused offline tests passed.
Focused mocked tests cover structural
requirements, exact current serialization, HTTP rejection without leakage or
stage inference, client parsing, successful domain mapping and evidence checks.

A future separately authorized diagnostic can be **one request**, not an A/B
pair, using [the prepared minimal request](groq-profile-minimal-probe-request.json).
It keeps the same endpoint, model, strict=true, service tier, output cap (1,500),
zero retries and no fallback. Input is only the synthetic text Backend engineer;
the schema has two required strings, headline and evidence, with extras forbidden.
This probe is diagnostic-only and must not be saved/applied as a profile suggestion.
Check both returned strings against the input; retain only validated synthetic
values and sanitized error metadata. Do not log unrestricted error/output bodies.

The 482-byte SDK serialization gives 2,530 estimated input tokens including the
existing 2,048 allowance, or 4,030 including the output cap, below 8,000 TPM.
At the planner's existing rate assumptions ($0.075/M input, $0.30/M output), exact
estimated cost is $0.00063975; upward-rounded ceiling is **$0.000640**. No account
pricing or actual usage is asserted. The production profile-only planner still
requires $0.000920 for its larger request; do not pass the probe budget to that
planner or silently replace its payload. The prepared probe needs a separately
reviewed one-shot diagnostic invocation, not a change to the production adapter.

Success would establish basic strict-output operation for this small contract,
not correctness of the full profile schema or any title theory. Failure would
narrow the problem toward the basic endpoint/contract path. Before a future
attempt, arrange to categorize any explanation in memory using fixed categories
(and optionally validate any bounded failed_generation in memory for sanitized
locations); the current report intentionally discards both fields. Raw content
must not be persisted. No probe or follow-up request was executed in this review.
