# Offline structural-label correction

The original OpenAI minimal-reasoning report storage/ai-evaluation/openai-pack-minimal-live-20260917-082604Z.json remains unchanged: that live request failed evidence validation. This task makes no new live request and does not relabel it as a success.

## Existing contract and deterministic correction

Allowed generic headings are Summary, Contact, Experience, Education, Skills, Projects, Languages, Cover letter, Curriculum vitae, Additional information. The UI and export renderers already render kind=heading deterministically. Contact is supported; Application for Backend Engineer is not a supported heading. Every nonheading block must have evidence.

Production validate_generated now canonicalizes only two precise structural cases on a copy, before applying the unchanged validators:

1. In the CV, an exact paragraph text Contact with empty evidence becomes the already-supported Contact heading. No trimming, case folding, prefix matching or short-paragraph heuristic.
2. In the cover letter, an exact evidence-free paragraph Application for <saved job title> is omitted only when a proper Cover letter heading already exists. A different title, an appended claim, or no Cover letter heading leaves the block untouched and subject to evidence validation. The subject is redundant job context, not a candidate qualification. No new dynamic heading is allowed.

Blocks with evidence are not removed or reclassified, so invalid references cannot be hidden by normalization. Revalidation after omission rejects heading-only documents. Factual prose, greetings, unsupported headings and arbitrary short paragraphs remain subject to existing checks. No evidence is generated, copied into missing slots, normalized or repaired. All other block text and evidence remain identical. Existing UI/export heading rendering handles the normalized documents; no frontend or exporter changes are necessary.

The production service stores the validated canonical output. Evaluation reports likewise store the canonical document and expose structural_labels_corrected, while the transport retains bounded redacted original provider text. Minimal reasoning stays in an evaluation-only subclass; production provider/defaults, pack prompt, schema and request token caps are unchanged by this structural fix.

## Retained result and replay limitation

The recoverable failing labels are cv.blocks[1] Contact and cover_letter.blocks[1] Application for Backend Engineer, both paragraphs with empty evidence. Actual contact fields and career claims had evidence, and the prior report independently checked 14 exact CV quotes. Those facts do not make the historical failure a pass.

The raw returned_text capture ends at its bound. The parsed output_redacted contains both documents but has redacted IDs, names, dates and prose; source-checked review recovers selected values but not the complete original output. Therefore an exact replay of retained unredacted documents is unavailable. No reconstruction is presented as original provider output.

Regressions use the two exact recovered labels in complete deterministic synthetic surrogate documents. They prove that only Contact.kind changes and the redundant subject is removed, all remaining text/evidence stay byte-for-byte equivalent at the model-dump level, and the raw input object is unchanged. Both Groq and OpenAI mocked SDK/evaluation paths pass these surrogates with the correction flag and canonical output. This is offline verification, not live success or an exact replay claim.

Negative cases include factual Contact prefixes, wrong job titles, appended PhD claims, standalone Python, unsupported technology/project prose, courtesy text, invalid evidence, unsupported headings, missing Cover letter heading, and heading-only output after omission. None receives an evidence exemption.

## Validation and remaining limits

86 distinct affected offline tests passed: 84 across structural labels, pack/profile diagnostics and evaluation; then two newly added mocked pipeline cases. No full suite was repeated. git diff --check passed. No provider requests were made; mocked transport calls remain offline.

The correction resolves the demonstrated representation issue, not general drafting quality. Exact evidence matching still cannot prove semantic entailment, and the earlier letter was mechanically worded. Unknown arbitrary prose remains uncorrected and must fail or be reviewed as appropriate. No full original replay or new live acceptance was demonstrated.

This closeout also commits the previously authorized OpenAI comparison harness and diagnostic-only minimal reasoning, together with their offline preparation artifacts/tests. These are related pending changes from earlier turns, not production reasoning changes. Unrelated documents, tools, scripts and Jira batch work are left untouched. No reset, restore, push, deployment, application sending or Jira change.
