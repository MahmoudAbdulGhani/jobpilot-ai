# Targeted strong/pack preparation (offline)

The latest live failure, storage/ai-evaluation/groq-pack-strong-live-20260917-073701Z.json, remains unresolved. HTTP 400 / json_validate_failed with an empty failed_generation neither proves truncation nor a request-schema rejection. No past report was changed. No new live request was sent.

## Proposed request

Actual GroqResponsesProvider.create_pack, exact existing strong fixture and unchanged prompt. Endpoint https://api.groq.com/openai/v1/responses, model openai/gpt-oss-20b. Add reasoning={"effort":"low"}, the documented nested Responses setting already exercised by profile. Official reference checked during preparation: https://console.groq.com/docs/responses-api#reasoning (example uses the same model).

Task-specific rationale: packs must emit two documents with claim references. Reserving more completion space and lowering reasoning effort tests whether this configuration can complete them. It is a proposed evaluation configuration, not a diagnosis or proven remedy for the unresolved failure. Because reasoning, annotations and cap change together, a future success would not isolate which change mattered.

OpenAI keeps its original PackProviderOutput serialization and no reasoning override. Groq fit and existing profile behavior remain unchanged. The higher completion cap is scoped to the pack-only Groq pilot; application-wide token settings and multi-task evaluations are unchanged.

## Semantic-preserving wire reduction

The schema already shares ProviderDocument between both documents, ProviderBlock between documents, and ClaimEvidence across blocks. No duplicate definitions need merging. GroqPackOutput removes only JSON Schema title annotations (display metadata), retaining actual property names including any property named title, definition names, references, required arrays, types, closed objects, patterns, enums, nullability, length and evidence bounds. It inherits all pack validators. No prompt instruction or synthetic fact changed. The response-format name becomes GroqPackOutput. This is metadata compaction, not a claimed fix for a title-keyword collision.

A test compares the final serialized schema against the retained baseline with only title annotations removed. Another proves a real title property survives. OpenAI wire schema equality is tested independently. Required-field checks before accepting defaulted data, source evidence validation, one-request guard, zero retries, no fallback and bounded redacted synthetic diagnostics remain intact.

## Final reservation

| Component | Prior | Proposed |
|---|---:|---:|
| Serialized bytes | 4,027 | 3,809 |
| Protocol allowance | 2,048 | 2,048 |
| Input reservation | 6,075 | 5,857 |
| Completion cap (includes reasoning) | 1,500 | 2,143 |
| Total reservation | 7,575 | 8,000 |
| Exact estimate USD | 0.000905625 | 0.001082175 |
| Upward-rounded budget USD | 0.000906 | 0.001083 |

2,143 is the maximum completion allowance under the unchanged reservation arithmetic for the final serialized request. There is zero reservation headroom; any serialization change must be replanned. The 2,048 allowance and 8,000 TPM ceiling are unchanged. These are conservative reservation estimates, not actual token usage or verified billing. Actual usage and cost remain unknown.

Dry artifact: groq-pack-low-dry-20260917.json; 1 planned strong/pack request, 0 requests sent. SHA-256: f92f5bb87e6b493d200cdca9fe2bfdf49f7c5aa6894535dc28622ab28094c04c.

## Exact commands

Working directory: C:\Users\Admin\Desktop\jobpilot-ai\backend

The dry run executed with sockets blocked is equivalent to:

```powershell
.venv/Scripts/python.exe -m app.evaluation.profile_diagnostic --task pack --output ../evidence/groq-pack-low-dry-20260917.json
```

For a newly authorized single live evaluation only (not executed here):

```powershell
$packGatePresent = Test-Path Env:JOBPILOT_EVAL_ALLOW_LIVE
$packGatePrevious = $env:JOBPILOT_EVAL_ALLOW_LIVE
$packStamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmssZ')
try {
    $env:JOBPILOT_EVAL_ALLOW_LIVE = '1'
    .venv/Scripts/python.exe -m app.evaluation.profile_diagnostic --task pack --live --dry-report ../evidence/groq-pack-low-dry-20260917.json --max-cost-usd 0.001083 --output "../storage/ai-evaluation/groq-pack-low-live-$packStamp.json"
} finally {
    if ($packGatePresent) { $env:JOBPILOT_EVAL_ALLOW_LIVE = $packGatePrevious }
    else { Remove-Item Env:JOBPILOT_EVAL_ALLOW_LIVE -ErrorAction SilentlyContinue }
}
```

The runner recomputes and matches the dry plan, requires its exact budget, loads the existing key privately, and stops after one attempt. Dry report creation is exclusive: use a new filename if refreshing it. Earlier budget authorization does not cover this larger proposed estimate.

Acceptance remains: provider completed, all wire-required fields present, complete CV and cover letter with body text, unchanged bounds/types, supported claims with semantically relevant references, valid exact source quotes or saved fact IDs, no unexplained omissions, and no refusal/incomplete/truncated output. Contract pass alone is not semantic acceptance or permission to send an application.

43 focused offline tests passed: pack diagnostics, shared profile diagnostics and pack provider contracts. They cover schema equivalence, preserved OpenAI behavior, complete-budget arithmetic, missing required/defaulted fields, invalid evidence, malformed/incomplete output, safe capture and no retry. No full suite repeated. git diff --check passed. Unrelated work preserved.
