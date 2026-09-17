# Offline OpenAI strong/pack comparison

Application-pack redesign paused. No production provider, pack prompt, fixture, schema, evidence validation or factual-review rule was changed in this task. No live request was made. Historical reports and unrelated work are preserved.

## Configuration and official verification

The configured OpenAI model and existing evaluator both use gpt-5-mini; configured/evaluation completion cap is 4,000. JOBPILOT_OPENAI_API_KEY is configured (presence only checked; value not displayed or saved). Key validity, account model access, rate tier and billing are unverified because no request was sent. No key setup is currently needed.

Official model page checked 2026-09-17: https://developers.openai.com/api/docs/models/gpt-5-mini. It lists Responses and Structured Outputs support, a 400,000 context window and 128,000 maximum output tokens. Standard text pricing per million tokens: $0.25 input, $0.025 cached input, $2.00 output. The plan assumes uncached input; no discount or free credits are assumed.

Existing OpenAIResponsesProvider.create_pack uses /v1/responses with PackProviderOutput, strict JSON schema, max_output_tokens=4000, store=false and service_tier=default. No reasoning effort, verbosity, temperature, tools or streaming override is sent. This preserves the existing adapter; no Groq-specific low-reasoning override or schema compaction is applied. Server reasoning effort remains unspecified in the request rather than asserted from another model's defaults.

The reasoning guide https://developers.openai.com/api/docs/guides/reasoning documents that the output allowance covers reasoning as well as visible output and reaching it can yield incomplete output. The existing 4,000 cap is retained for comparison, not claimed sufficient for success.

## One-request plan

Artifact: openai-pack-comparison-dry-20260917.json. Exactly one planned request, strong/pack, same fixture and application-pack-v2 prompt as Groq. Actual requests: zero. Final SDK serialization is captured with a mock transport and sockets blocked.

- Serialized bytes: 4,498; allowance: 2,048; estimated input reservation: 6,546.
- Evaluation input guard: 32,000; maximum output: 4,000; this request total reservation: 10,546.
- Groq's 8,000 TPM assumption does not apply to the separate OpenAI endpoint. OpenAI account limits remain unverified.
- Specific serialized-request estimate at full completion cap: (6546 * 0.25 + 4000 * 2) / 1,000,000 = $0.0096365; rounded upward to six decimals $0.009637.
- The unchanged OpenAI planner uses its broader 32,000-input allowance for authorization: (32000 * 0.25 + 4000 * 2) / 1,000,000 = $0.016. The exact required budget argument and proposed authorization ceiling is therefore USD 0.016 for one request, not $0.009637.
- Actual usage, cached-token savings and billed cost are unknown.
- SHA-256: a0826c36f4f18aa2065e72a9b67fb9af153ecb18ee4a8657793ac62e9a4eebc7.

This compares the existing adapters/configurations, not equal token budgets: OpenAI has 4,000 completion tokens and unspecified reasoning versus Groq's prepared low/1,664. Outcome differences cannot be attributed to model quality alone.

## Checks and diagnostic scope

Only the synthetic evaluation harness gained --provider openai support (pack-only). It uses the unchanged production OpenAI adapter, canonical OpenAI endpoint and one-attempt hash guard. SDK/transport retries remain zero, redirects disabled, timeout 60 seconds, no fallback. It uses the same recursive explicit-required-field check, production evidence validation and bounded redacted capture as Groq. Production routes/configuration are unchanged.

Automated acceptance requires completed status, valid JSON, both documents with bounded body blocks, every wire-required field explicitly present, valid evidence on all factual/body blocks, exact contiguous CV quotes and known saved fact IDs. Missing required defaults cannot conceal incomplete output. Semantic review remains separate: contacts and career claims must be supported, role/project associations correct, no unsupported skill/project join, no stitched quotes, complete usable documents without observed truncation. Valid references alone do not establish truth. Beirut's omission alone is not a demonstrated requirement defect. No output is applied or sent automatically.

49 focused offline tests passed with sockets blocked: both providers' diagnostic success/failure paths, missing required fields, invalid evidence, malformed/incomplete output, safe capture, canonical endpoints and preserved existing profile behavior. git diff --check passed. No full suite repeated.

## Exact commands

Working directory: C:\Users\Admin\Desktop\jobpilot-ai\backend

Dry command already executed (use a new output filename to refresh):

```powershell
.venv/Scripts/python.exe -m app.evaluation.profile_diagnostic --provider openai --task pack --output ../evidence/openai-pack-comparison-dry-20260917.json
```

Prepared live command, requiring separate user authorization for one request with USD 0.016 ceiling; not executed:

```powershell
$packGatePresent = Test-Path Env:JOBPILOT_EVAL_ALLOW_LIVE
$packGatePrevious = $env:JOBPILOT_EVAL_ALLOW_LIVE
$packStamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmssZ')
try {
    $env:JOBPILOT_EVAL_ALLOW_LIVE = '1'
    .venv/Scripts/python.exe -m app.evaluation.profile_diagnostic --provider openai --task pack --live --dry-report ../evidence/openai-pack-comparison-dry-20260917.json --max-cost-usd 0.016 --output "../storage/ai-evaluation/openai-pack-comparison-live-$packStamp.json"
} finally {
    if ($packGatePresent) { $env:JOBPILOT_EVAL_ALLOW_LIVE = $packGatePrevious }
    else { Remove-Item Env:JOBPILOT_EVAL_ALLOW_LIVE -ErrorAction SilentlyContinue }
}
```

The runner recomputes and compares the dry plan before sending. It loads the existing private key internally and refuses a mismatched budget/plan. No automatic rerun or provider switch. No reset, restore, push, deployment, sending or Jira changes.
