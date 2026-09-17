# Strong/pack evidence failure: offline review and v2 preparation

The original storage/ai-evaluation/groq-pack-low-live-20260917-074430Z.json and .md are preserved unchanged. The earlier HTTP400/empty failed generation remains unresolved; the latest HTTP200/completed response proves only that this particular response parsed, not the earlier failure's cause.

## Classification from retained evidence (zero-based indexes)

| Location | Retained evidence | Classification |
|---|---|---|
| cv.blocks[3] | Synthetic name and email, empty evidence | Factual contact data present in CV; missing references. Not a greeting. |
| cv.blocks[14] | Body bullet under Languages, text redacted, empty evidence | Exact wording unavailable. Could be a language claim or placeholder; cannot prove either. Source has no language fact. It is not identifiable as letter courtesy text. |
| cover_letter.blocks[2] | Final paragraph with visible self-assessment fragments and closing language, empty evidence | Mixed/uncertain semantics. Not demonstrated to be purely non-factual thanks/greeting. Unredacted wording was not retained, so no exact claim reconstruction is justified. |

The diagnostic redaction is intentionally conservative. English and the sample self-assessment used in new tests are synthetic boundary cases, not claims that those exact strings were returned.

Both cv.blocks[5].evidence[0].cv_quote and cover_letter.blocks[1].evidence[0].cv_quote combine `Engineer at Cedar Demo, 2021-2024; built a booking API`. This equals saved fact-4's value. The actual CV has `Engineer at Cedar Demo, 2021-2024` followed by a newline and `Project: built a booking API`. The joined semicolon string is not a contiguous CV quote. A valid fact ID alongside an invalid quote does not make the quote valid. Separate exact excerpts or fact-4 with cv_quote=null are valid representations; the runtime does not repair returned evidence.

The unsupported technology relationship is in cover_letter.blocks[1], in the clause joining the booking API to Python and PostgreSQL. The retained sentence places both technologies with the project; exact joining words are redacted. Facts 2/3 establish global skills and fact-4 establishes role/project, not that those technologies were used for the project. The paragraph attaches only fact-4 and the invalid combined quote. Even attaching all three facts would not establish the relationship.

Beirut is absent from the generated CV. This is an observed omission, not a demonstrated requirement violation: the prompt required preserving contacts and relevant projects but did not explicitly require the location field or every source fact. This review qualifies the earlier report's stronger content-completeness label without rewriting historical evidence.

## Smallest correction and scope

The production pack prompt already required factual support, exact CV quotes and evidence on every nonheading block. These output failures are not evidence that validation is too strict. The prompt lacked explicit guidance for cross-fact joins, confusing profile fact values with CV excerpts, and non-factual letter boilerplate. application-pack-v2 now:

- Keeps facts attached only to explicitly supported roles/projects; unassigned global skills remain unassigned.
- Requires exact contiguous excerpts for CV-derived facts, using separate references for separate excerpts.
- References saved facts by supplied fact_id and leaves cv_quote null unless it is also an exact CV excerpt.
- Forbids turning separately supported facts into unsupported relationships.
- Omits genuinely non-factual greetings, thanks and sign-offs because this contract has no evidence-free body kind. It never invents evidence for courtesy text, exempts factual body blocks or disguises claims as headings.
- Places missing/unsupported information in review_notes rather than inventing language or achievement claims.

No schema/domain/evidence validation was weakened, no evidence was filled in, and no quote was normalized or repaired. No new factual input or structured association was invented. Association is a generation instruction using existing source relationships, not an inferred preprocessing step. The prompt revision applies to production pack generation for both providers; OpenAI's schema, reasoning and token settings remain unchanged. Profile and fit are unchanged.

This commit also includes the previously prepared, exercised Groq-only low-reasoning option and title-annotation-only wire compaction. Definition/property names, types, references, required fields, and bounds remain equivalent, as tested. Those changes were already present during the latest live request. The v2 correction itself is the prompt plus its version, tests and recalculated pack-only evaluation cap.

## Focused regressions and limits

51 tests passed across test_pack_diagnostic.py, test_profile_diagnostic.py and test_pack_provider.py. Coverage includes both invalid combined-quote locations even with a valid fact ID; missing evidence on factual contacts, synthetic language/self-assessment examples, and courtesy text; exact separate excerpts without repair; required/defaulted wire fields; no retry; safe diagnostics; schema equivalence and unchanged other capabilities. A regression explicitly documents that valid fact IDs alone cannot detect an unsupported technology/project join. The revised instruction and explicit user review address that semantic boundary; no automated factual-quality guarantee is claimed.

No full suite or live calls were run. git diff --check passed. Source excerpts, references and complete JSON remain necessary but insufficient for semantic correctness. Prompt adherence and editorial quality remain unverified for v2. Output truncation is still possible; no success is promised.

## Revised dry plan

Artifact: groq-pack-v2-dry-20260917.json. One planned strong/pack request, zero sent. Actual production adapter, openai/gpt-oss-20b Responses endpoint, reasoning effort low; completion cap 1,664. Required-field checks, exact evidence validation, bounded redacted capture, zero retries and no fallback remain enabled.

Final bytes 4,288 + unchanged allowance 2,048 = input reservation 6,336. Maximum fitting completion is 1,664. Total reservation 8,000, no headroom. Prompt growth adds 479 input bytes versus the previous low-reasoning request; completion reservation decreases from 2,143 to 1,664. Correctness instructions were not removed to retain the old cap.

Exact estimate $0.0009744; upward-rounded budget $0.000975 at assumed rates $0.075/M input and $0.30/M output. Actual usage and billing remain unknown. SHA-256: 160b82473981218b6a9d8ffe28655dd047cb5b15b57bf0d1d0c90e9e65aad02c.

Working directory C:\Users\Admin\Desktop\jobpilot-ai\backend. Dry command (already executed with sockets blocked; choose a new output filename to refresh):

```powershell
.venv/Scripts/python.exe -m app.evaluation.profile_diagnostic --task pack --output ../evidence/groq-pack-v2-dry-20260917.json
```

For a future separately authorized single request only, with the live gate enabled and restored in finally:

```powershell
.venv/Scripts/python.exe -m app.evaluation.profile_diagnostic --task pack --live --dry-report ../evidence/groq-pack-v2-dry-20260917.json --max-cost-usd 0.000975 --output ../storage/ai-evaluation/groq-pack-v2-live-UNIQUE-UTC-TIMESTAMP.json
```

No live call, reset, restore, push, deployment, sending or Jira changes. Unrelated work preserved.
