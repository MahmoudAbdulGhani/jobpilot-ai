# OpenAI pack checkpoint and application integration

## Retained successful case

The [unaltered acceptance summary](openai-pack-acceptance-live-20260917-083313Z.md)
records the single strong synthetic request from checkout 63196df. Original JSON,
Markdown and dry-run artifacts remain in ignored `storage/ai-evaluation/`.
This integration task made **zero live AI requests**.

The prior request returned HTTP 200/completed with required fields present,
12 CV blocks and a three-block cover letter. The actual pack validator passed,
including exact source quotes for all 14 evidence entries. Structural
normalization ran but made no changes. Source review found no unsupported career
claim or erroneous Python/PostgreSQL-to-project association. All synthetic CV
facts were represented; no provider truncation was observed. Usage was 870 input,
1,451 output and zero reasoning tokens, with a usage-based estimate of
USD 0.0031195; actual billing remains unknown.

Quality limitations: the letter is readable but brief and generic, with little
employer-specific persuasion; the CV groups skills into a multiline bullet and
repeats project content. One synthetic success is not evidence of general
readiness. Bounded raw-text capture was truncated, although the parsed-output
capture and source review covered both documents. No documents were approved,
applied or sent by that live evaluation.

## Integration

- New independent pack settings select OpenAI, `gpt-5-mini`, explicit
  `reasoning={"effort":"minimal"}`, 4,000 completion tokens and a 60-second timeout.
  Only OpenAI is accepted by the application pack-provider setting.
- The existing Responses adapter, prompts, schema, completeness rejection,
  structural normalization and exact-evidence validation are reused. Profile and
  job-fit settings/defaults and their request construction are unchanged.
- Global AI enablement, input limit, shared per-user quota and guarded test
  provider still apply. The quota lease and generation deadline cover the pack
  timeout. Missing credentials fail closed; zero retries and no fallback.
- Options disclose provider/model and generated packs persist them. Stored prompt
  metadata now uses the actual adapter prompt version (`application-pack-v2`).
- Review/edit/explicit approval and approved-version PDF/DOCX exports remain
  intact. No automatic approval or application sending was introduced.
- Private `.env` and AI enablement were left untouched. `.env.example` and README
  document configuration without credentials. No live gate was changed.

## Offline verification

Affected backend tests: 130 passed across `test_pack_configuration`,
`test_pack_provider`, `test_pack_structural_labels`, `test_pack_export`,
`test_config`, `test_pack_diagnostic`, `test_profile_diagnostic` and
`test_ai_evaluation`. Separately, all 64 `test_groq_provider` tests passed.
Only an existing Starlette/httpx deprecation warning was reported.

The new configuration tests intercept the real SDK HTTP transport, assert the
OpenAI endpoint/model/minimal reasoning/4,000 cap/60-second timeout/strict schema
and zero retries, and block socket connections. They verify independent shared
configuration, missing-key and disabled-AI rejection, invalid settings, and the
test-provider guard. Groq tests now account for the existing v2 wire-model class
and longer prompt; the 8,000-token guard is retained, and selection-order tests
isolate selection from unrelated budget calculations.

Frontend: all 24 unit tests passed. The connected Chromium application-pack
scenario passed against the guarded deterministic provider and test database:
generate -> review -> edit/save -> reload -> explicit approval -> download and
inspect PDF and DOCX. It verifies provider disclosure and absence of export
buttons before approval. The browser scenario proves application flow with a
test provider, not new OpenAI quality or reliability.

Commands from repository root (frontend commands from `frontend`):

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_pack_configuration.py backend/tests/test_pack_provider.py backend/tests/test_pack_structural_labels.py backend/tests/test_pack_export.py backend/tests/test_config.py backend/tests/test_pack_diagnostic.py backend/tests/test_profile_diagnostic.py backend/tests/test_ai_evaluation.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_groq_provider.py -q
# From frontend:
npm test -- --run
npx playwright test tests/e2e/application-packs.spec.ts
```

No production deployment, provider call, application sending or Jira action was
performed. Unrelated work is excluded from this commit.
