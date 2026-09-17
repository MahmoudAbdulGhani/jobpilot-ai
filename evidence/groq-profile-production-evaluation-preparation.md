# Production-profile evaluation prepared offline

No live request was made. The production GroqResponsesProvider and unchanged
strong synthetic fixture are used by app.evaluation.profile_diagnostic. The
module only permits profile/strong, never accepts arbitrary CV input, and defaults
to a dry run. Production routes and logging do not import it.

## Demonstrated defect and scope

The production wire already required evidence arrays with minItems=1/maxItems=10.
Compaction discarded Evidence.quote's minLength=1/maxLength=1000 even though local
parsing required those bounds. Consequently the provider wire could accept an
empty quote that the application would reject. Removed that evidence-specific
constraint stripping. No validator was relaxed; no evidence is auto-filled.

No new correctness constraint was stripped or shortened to meet the estimate.
The pre-existing local-only ID constraints, suggestion-count bound and some other
string minima remain unchanged; this fix is specifically the evidence contract.
The strong fixture and production instructions are unchanged. Explicit user review,
source-quote validation, required fields and provider selection are unchanged.

[Groq structured-output documentation](https://console.groq.com/docs/structured-outputs)
lists the model, required properties and closed objects, but does not explicitly
confirm minLength/maxLength support. These standard bounds are restored for the
prepared evaluation rather than declaring their omission necessary. Deployment
support is not proven offline. A provider rejection naming the keyword would be
evidence of an incompatibility; HTTP 400 by itself would not be. This preparation
makes no claim that the earlier failure is fixed or that one request guarantees
a conclusive root cause if the provider omits details.

## Final dry run and budget

Saved report: groq-profile-production-evaluation-dry.json.
Actual SDK-serialized request: groq-profile-evidence-bounds-request.json.
SHA-256: 071bb0ad02a2cee7663340297c729a233fb846945788bd480d582720feb2d41f.

| Reservation component | Value |
| --- | ---: |
| Serialized request UTF-8 bytes | 4,243 |
| Existing conservative protocol allowance | 2,048 |
| Input token estimate | 6,291 |
| Maximum output, including reasoning | 1,500 |
| Complete token reservation | 7,791 |
| Existing TPM limit | 8,000 |
| Remaining capacity | 209 |
| Exact estimate at existing assumed rates | $0.000921825 |
| Decimal upward-rounded budget argument | $0.000922 |

Existing rate assumptions are $0.075/M input and $0.30/M output. Actual account
pricing and billed cost are not established. No instructions, facts or output
allowance had to be removed to fit this final evidence-restored request.

## Bounded synthetic failure capture

The dedicated transport checks the exact request hash and endpoint and permits
at most one HTTP attempt. Redirects, retries and fallback are disabled; the
existing TokenScheduler reserves 7,791 tokens. A matching saved dry plan and the
explicit live gate/budget are mandatory. Output report paths are exclusive.

Capture occurs before SDK parsing: HTTP status and bounded integer usage remain
available even if parsing fails. Only the provider error message (2,048 chars),
failed_generation (4,096 chars), and returned output/refusal text (4,096 chars)
are retained after conservative redaction. Unknown words, names, addresses,
numbers and supplied credential values are redacted. JSON punctuation and known
schema/diagnostic words remain. This can remove useful unfamiliar details; the
report must not infer them. Headers, reasoning text and unrestricted bodies are
never persisted. Responses over 128 KiB skip body capture with an explicit marker.
Generated result dumps are also redacted before saving in this diagnostic.

When a bounded failed_generation is supplied, it is validated in memory against
the actual provider model. Only sanitized validation locations/types, pass/fail,
and evidence-check results are retained in addition to the redacted text. Nothing
from the failed generation is accepted or applied as a profile suggestion.

## Interpretation

- An explanation explicitly rejecting a schema keyword/shape supports a
  request-schema failure. The HTTP status or json_validate_failed alone does not.
- An explanation about generated JSON, plus a failed generation with observable
  syntax/field violations, supports output-validation failure. Local validation
  of retained failure content does not prove which server-side check failed.
- HTTP success followed by sanitized Pydantic errors identifies client parsing
  failure; captured status/usage prevent confusion with transport rejection.
- Successful parsing followed by source-check failure is invalid evidence.
- contract_pass plus nonempty/partial checks establishes the local contract only.
  It does not verify semantic completeness, tailoring quality or all source facts;
  human review and explicit selection remain necessary. Empty/partial output is
  reported, not automatically retried.

Unknown or missing explanation/generation/usage remains unknown. No automatic
adapter change or retry is justified solely by a failure status.

## Exact future command (not executed)

From the repository root in PowerShell, after separate live authorization:

```powershell
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmssZ')
$env:JOBPILOT_EVAL_ALLOW_LIVE = '1'
& .\backend\.venv\Scripts\python.exe -m app.evaluation.profile_diagnostic --live --dry-report .\evidence\groq-profile-production-evaluation-dry.json --max-cost-usd 0.000922 --output ".\storage\ai-evaluation\groq-profile-production-$stamp.json"
```

Credentials are loaded through the existing environment/.env mechanism; none
belong in the command. This entrypoint fixes profile-only/strong in code. It will
refuse if the current serialized request or plan no longer matches the dry report.

## Verification

160 affected offline tests passed; five database integration tests were excluded.
Coverage includes actual serialized evidence bounds, preserved strong source,
exact-source acceptance, empty/missing/out-of-source evidence rejection,
HTTP request-schema versus generated-output examples, SDK parse failures with
available usage, bounded secret/PII redaction, one-attempt enforcement, and live
gate/dry-plan/budget checks. Tests use blocked sockets and MockTransport.
Unrelated work and previous diagnostic artifacts were preserved.
