# OpenAI pack comparison: explicit minimal reasoning (offline)

No live requests sent. Historical reports and unrelated work preserved. Production provider, production adapter defaults and other AI capabilities are unchanged.

Official verification: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5 names gpt-5, gpt-5-mini and gpt-5-nano as the family and lists reasoning.effort values minimal, low, medium and high. Minimal is the lowest supported level; none is not selected. For this bounded source-based drafting comparison, minimal is a justified experiment after the preceding run consumed 3,648 of 4,000 output tokens on reasoning. It does not guarantee completion or factual accuracy.

Exact request setting: reasoning={"effort":"minimal"} on Responses, model gpt-5-mini. No Chat-style reasoning_effort parameter is sent. An evaluation-only subclass changes only _pack_request_options; planning, MockTransport serialization and execution use the same subclass through an explicit pack-only pilot option. Production adapters are not modified. The dedicated diagnostic selects the option, while ordinary evaluation defaults remain unchanged.

The same strong fixture, application-pack-v2 prompt, original OpenAI PackProviderOutput schema, strict required-field checks and production evidence validator remain. Final serialized-request regression proves the sole payload change from the retained previous OpenAI dry plan is the reasoning object. Incomplete/max_output_tokens remains a rejection even if supplied text is otherwise valid JSON. No repair, retry or fallback is introduced.

## Final one-request dry plan

Artifact: openai-pack-minimal-dry-20260917.json. Planned requests: 1 (strong/pack). Actual sent: 0. Serialized bytes 4,531 plus unchanged 2,048 allowance = input estimate 6,579. Completion cap 4,000 (reasoning plus visible output). Total reservation 10,579. Evaluation input guard remains 32,000. Groq's 8,000 TPM assumption does not apply to OpenAI; actual account limits are unverified.

Request-specific maximum estimate: (6579 * $0.25/M + 4000 * $2/M) = $0.00964475; upward-rounded six-decimal estimate $0.009645. The unchanged conservative OpenAI planner uses its 32,000-input guard and 4,000-output cap for a required budget argument of $0.016. Actual usage and billed cost remain unknown. Existing rates were verified in the preceding preparation at https://developers.openai.com/api/docs/models/gpt-5-mini.

Hash: 0834361bb94d9a700e14789104c0b4beb0f9ae9f0d059f43373ed05042d0b193. No explicit temperature/verbosity override; store=false, service_tier=default, no tools, timeout 60 seconds, SDK and transport retries zero. The canonical endpoint and exact request hash guard permit only one attempt. Bounded redacted synthetic diagnostics are unchanged.

## Commands

Working directory: C:\Users\Admin\Desktop\jobpilot-ai\backend

Dry run already executed with sockets blocked; choose a new filename when refreshing:

```powershell
.venv/Scripts/python.exe -m app.evaluation.profile_diagnostic --provider openai --task pack --output ../evidence/openai-pack-minimal-dry-20260917.json
```

Prepared future one-request command; needs new live authorization and was not executed:

```powershell
$packGatePresent = Test-Path Env:JOBPILOT_EVAL_ALLOW_LIVE
$packGatePrevious = $env:JOBPILOT_EVAL_ALLOW_LIVE
$packStamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmssZ')
try {
    $env:JOBPILOT_EVAL_ALLOW_LIVE = '1'
    .venv/Scripts/python.exe -m app.evaluation.profile_diagnostic --provider openai --task pack --live --dry-report ../evidence/openai-pack-minimal-dry-20260917.json --max-cost-usd 0.016 --output "../storage/ai-evaluation/openai-pack-minimal-live-$packStamp.json"
} finally {
    if ($packGatePresent) { $env:JOBPILOT_EVAL_ALLOW_LIVE = $packGatePrevious }
    else { Remove-Item Env:JOBPILOT_EVAL_ALLOW_LIVE -ErrorAction SilentlyContinue }
}
```

The entrypoint recomputes and compares the full dry plan, including reasoning selection and serialized hash. Old omitted-reasoning dry plans cannot authorize this request. Credentials load privately as before. Full document completeness and semantic support still require separate review; quote matching alone is insufficient.

Validation: 72 affected offline tests passed (50 pack/profile diagnostic tests, 22 evaluation tests). Tests verify minimal in actual SDK serialization and mocked execution, no other payload changes, incomplete/max_output_tokens rejection, required-field/evidence failures, redaction, no retry and existing capability defaults. git diff --check passed. No full suite repeated.

Changes remain uncommitted with earlier comparison harness work preserved. No live calls, reset, restore, push, deployment or Jira changes.
