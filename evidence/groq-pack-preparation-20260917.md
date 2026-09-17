# Strong application-pack evaluation prepared offline

No live requests were made in this task. The profile closeout is committed separately; its original timestamped reports remain untouched, with durable copies in groq-profile-success-20260917.json and .md. That one case passed HTTP, wire and local evidence checks. Its two quality caveats remain: combined skills in one entry, and a project note absent from the experience evidence quote. It does not demonstrate general readiness.

## Actual production request and settings

The shared synthetic diagnostic now accepts --task pack (profile remains the default). It calls evaluation.dispatch -> GroqResponsesProvider.create_pack with the existing strong fixture, unchanged production prompt, PackProviderOutput and SDK strict JSON schema. It does not use profile suggestions as pack inputs: the fixture's saved facts remain independent. No production pack setting, adapter, schema, prompt, source fact or logging policy changed.

Endpoint: https://api.groq.com/openai/v1/responses
Model: openai/gpt-oss-20b
Completion cap: 1,500, including reasoning. Reasoning effort: omitted; server default is not asserted or measured. Profile-only low reasoning remains profile-only.
Strict: true; store: false; service_tier: default; no tools; zero retries; no fallback; timeout 60 seconds; transport permits one request with the prepared SHA-256 only.

Profile's retained explanation demonstrated exhaustion at 1,500 tokens for that earlier profile request. Packs generate two evidence-bearing documents and remain at risk of truncation at this cap. It does not establish that packs fail, nor prove a higher cap is sufficient. This baseline measures the existing pack contract before any task-specific tuning. With unchanged input, at most 1,925 completion tokens could fit the current reservation arithmetic; copying profile's 2,250 cap would reserve 8,325 and exceed 8,000. No setting was changed merely to imitate profile success.

## Final serialized dry run

Saved: groq-pack-strong-dry-20260917.json. Prepared request count: 1 (strong/pack); actual requests: 0.
Serialized bytes: 4,027; protocol allowance: 2,048; input reservation: 6,075; output reservation: 1,500; total: 7,575; headroom: 425 under 8,000 TPM.
Exact cost estimate: $0.000905625; upward-rounded budget argument: $0.000906. Rates are planner assumptions ($0.075/M input, $0.30/M output), not verified billing. Actual usage and cost remain unknown.
SHA-256: 1ed5fc96b24e7628397eff56ca3f0905c3336e6f2469311ab5e7bae22da64ad2.

## Acceptance and failure evidence

A contract pass requires provider completed status, well-formed output, every required wire field (including explicit nullable evidence keys and review_notes), both nonempty documents with body text, bounded typed blocks, valid unique IDs/headings, and unchanged production evidence validation. Defaulted fields must not conceal omissions. The diagnostic recursively checks fields_set after parsing raw generation, and overrides an apparent contract pass if required-field checking or evidence verification fails or cannot be performed within capture limits. Mocked completed responses missing review_notes or nullable fact_id demonstrate this diagnostic gap and its fix. Production parsing behavior is unchanged.

Full evaluation acceptance additionally requires offline semantic review of both documents: a complete usable CV and cover letter; source contacts, location, both skills, employer/role/dates, project and education retained appropriately; job-specific emphasis grounded only in saved facts/CV; no invented metrics, achievements, recipients or qualifications; each factual claim actually supported by its attached references; no silently omitted relevant facts or unresolved conflicts; no truncation, refusal or incomplete ending. Empty evidence is permitted only for generic headings. Both documents require explicit user review before use. A contract_pass alone is not semantic acceptance.

Transport capture retains HTTP status, provider status, bounded usage, provider explanation (2,048 chars), failed generation/returned text (4,096 chars), and sanitized validation locations. Unknown words/addresses/secrets are redacted; no headers, credentials, unrestricted bodies or reasoning text are recorded. Body inspection is capped at 128 KiB and local raw-generation inspection at 32,768 characters. Failed generation is checked with the pack model, not the profile model. HTTP code alone does not distinguish request-schema rejection from generated-output failure: consult safe error code/type, provider explanation, failed generation and local required-field/evidence diagnostics. Missing provider detail remains an explicit limitation.

## Commands (prepared only; live needs separate authorization)

Verified working directory: C:\Users\Admin\Desktop\jobpilot-ai\backend
Dry run (choose a new report filename on repetition because creation is exclusive):

```powershell
.venv/Scripts/python.exe -m app.evaluation.profile_diagnostic --task pack --output ../evidence/groq-pack-strong-dry-20260917.json
```

Exactly one future request with a timestamped result and restored gate:

```powershell
$packGatePresent = Test-Path Env:JOBPILOT_EVAL_ALLOW_LIVE
$packGatePrevious = $env:JOBPILOT_EVAL_ALLOW_LIVE
$packStamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmssZ')
try {
    $env:JOBPILOT_EVAL_ALLOW_LIVE = '1'
    .venv/Scripts/python.exe -m app.evaluation.profile_diagnostic --task pack --live --dry-report ../evidence/groq-pack-strong-dry-20260917.json --max-cost-usd 0.000906 --output "../storage/ai-evaluation/groq-pack-strong-live-$packStamp.json"
} finally {
    if ($packGatePresent) { $env:JOBPILOT_EVAL_ALLOW_LIVE = $packGatePrevious }
    else { Remove-Item Env:JOBPILOT_EVAL_ALLOW_LIVE -ErrorAction SilentlyContinue }
}
```

The entrypoint recomputes the final request/plan and refuses a changed dry plan or budget. It loads the existing private key internally. Never automatically rerun on failure.

Validation: 28 affected offline tests passed (11 pack diagnostic cases and 17 profile diagnostic regressions for the shared harness), with sockets blocked. No full suite was repeated. git diff --check passed. No live calls, reset, restore, push, deployment or Jira changes.
