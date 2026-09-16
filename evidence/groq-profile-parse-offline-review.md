# Groq profile parse: offline review, 2026-09-16

No live requests were made. Existing reports and unrelated checkout work were
preserved. This review independently inspected the current implementation,
installed SDK source, and both stored pilot reports; it does not adopt the
previous diagnosis as proof of the later failure.

## Retained evidence and limits

`storage/ai-evaluation/groq-pilot-live-20260916-165449.json` records one profile
attempt, `provider_failure`, `ValidationError`, null usage, and no HTTP status.
No generated output, field location, or validation model was retained. The
historical `transport_or_parse_failure` label does not establish HTTP success.
The precise failing field and whether JSON syntax, a model constraint, or an
envelope problem caused this failure remain unknown. Tokens and actual cost
also remain unknown; a cost reservation is not measured usage.

The earlier `groq-pilot-live-20260916-145452.json` records a profile
`validation_failure` with provider status `completed`, 508 input tokens and
1097 output tokens. Its retained suggestions contain string experience and
education values. That is evidence about the earlier result only. It does not
establish the content of the later failed response. That older report continued
to fit and pack; the current stop-on-failure behavior is covered separately.

## SDK boundary inspected

Installed versions: OpenAI Python 2.54.0, Pydantic 2.13.4.

- `openai/resources/responses/responses.py`: `parse()` registers a post-parser.
- `openai/_base_client.py`: envelope construction/strict validation can raise
  Pydantic `ValidationError`, wrapped as `APIResponseValidationError` with an
  HTTP response. Default envelope construction is permissive, not strict.
- `openai/lib/_parsing/_responses.py`: the post-parser passes output text to
  `model_parse_json(text_format, text)`. Both malformed JSON (`json_invalid`)
  and typed-model violations raise Pydantic `ValidationError` here.
- The application subsequently calls `ProviderSuggestionOutput.model_validate`;
  its errors are also wrapped in `ProviderFailure`. A returned response's status
  and usage have already been captured by the evaluation meter at this point.

An SDK content-parse exception does not expose the response to the caller.
The integration is unchanged: the meter reports status `unknown`, HTTP status
null, and usage null in that case. If the SDK exception exposes an HTTP status,
it is retained (the mocked strict-envelope failure exposes HTTP 200); this does
not imply a valid response. For envelope errors the SDK also exposes a body:
known status enums and nonnegative bounded integer token counts are retained
from it without copying other content. Available returned response status and
usage survive subsequent application validation failures.

## Diagnostics now retained

Reports include exception class and, for a Pydantic error in the cause chain,
`validation.model` plus `validation.errors`: built-in error `type`, sanitized
`location`, and `location_truncated`. `errors_truncated` marks omitted entries.
Model/field names come from trusted local schemas, not arbitrary response text.
Unknown names are redacted, unknown model/custom error types become `unknown`.
At most 20 errors and 8 location components per error are retained; field names
are limited to 80 characters and integer indices to 0–10000.

Extraction uses `errors(include_input=False, include_context=False,
include_url=False)`. Messages, input values, contexts and URLs are never copied.
Short arbitrary provider error type/code strings are also discarded, since
length limits alone cannot prevent credential leakage. Untagged union errors
can describe several candidate branches; a listed branch is not proof that it
was the generated suggestion's intended type. Malformed JSON has an empty
location because no field can be reliably identified.

## Compact schema discrepancy

Compaction removes real constraints, not just informational metadata:

| Constraint omitted on wire | Still enforced locally |
| --- | --- |
| Suggestion ID min/max length and pattern | 1–64 characters, ASCII letters/digits/underscore/hyphen |
| Suggestions maxItems | At most 50 |
| Evidence quote min/max length | 1–1000 characters |
| Headline/location/skills value minLength | At least 1 character |

It also removes title/default/description metadata. Typed value references,
field literals, required fields, extra-property rejection, evidence list bounds,
string value maxima, and nested entry constraints remain. The SDK's strict
conversion makes all properties required; local optional defaults still exist.
An output token cap does not guarantee the omitted count/length constraints.
Thus wire-compliant output can fail local parsing. Application validation and
the emitted wire schema have not been weakened or changed by this fix.

## Verification and review

92 affected offline tests passed; five database integration tests were excluded.
Tests used blocked sockets and synthetic credentials. Real SDK MockTransport
cases cover malformed JSON, wrong field types, empty values, invalid IDs,
oversize quotes, excess suggestion count, sensitive extra-property names, and
strict envelope validation. Every failure checkpoint stops after one attempt;
no fit/pack continuation, retry, or fallback occurs. Additional tests verify
metadata truncation/redaction and retained status/usage/cost after a returned
response fails local validation. Existing schema and provider tests also pass.

Final review checked exception wrapping, report merge order, bounds, privacy,
schema omissions and stored evidence independently of earlier conclusions.
No provider replacement, schema relaxation, report overwrite, or retrospective
claim about the missing response was made. `git diff --check` passed.
