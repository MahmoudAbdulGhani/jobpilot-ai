# OpenAI strong/pack acceptance ? 2026-09-17 08:33:13 UTC

Exactly one new live HTTP request from checkout 63196df. Model gpt-5-mini, returned gpt-5-mini-2025-08-07; diagnostic reasoning minimal; completion cap 4,000; unchanged strong fixture, application-pack-v2 prompt and schema. Zero retries, no fallback, production defaults unchanged.

Fresh dry report openai-pack-acceptance-dry-20260917-083227Z.json. Final serialized hash 0834361bb94d9a700e14789104c0b4beb0f9ae9f0d059f43373ed05042d0b193. Request reservation 6,579 input + 4,000 completion = 10,579; specific maximum estimate $0.00964475; conservative planner ceiling $0.016, within authorization.

## Provider completion and required fields

HTTP 200, provider completed, no incomplete reason or provider error explanation. Both documents and review_notes parsed. Explicit wire-required fields passed the raw-generation completeness check. CV: 12 blocks; cover letter: 3 blocks (heading plus two body paragraphs). No observed provider output truncation. Bounded raw-text diagnostic capture is truncated, but full parsed-output diagnostics and source-checked review cover both documents.

## Structural normalization

The actual production canonical_structural_labels/validate_generated path ran. No normalizations were needed: zero label conversions and zero omissions, structural_labels_corrected=false. Repeated validation produced the same unchanged result. This is a live exercise of the path, not new evidence of correcting the previously failing labels on a live response.

## Evidence validation

contract_pass. Every nonheading block has evidence. All supplied non-null CV quotes matched exact contiguous source excerpts; known fact IDs passed validation. Name/email/location have individual supporting excerpts. Role and project use separate exact passages, not stitched quote strings. No evidence was repaired or auto-filled. Contract acceptance does not imply user approval.

## Separate factual and quality review

No unsupported career claim was identified in reviewable content. The role/project association with Cedar Demo is established by saved fact-4. Python and PostgreSQL remain general skills; the output does not attach them to project implementation. Review notes explicitly call out that missing association.

The CV represents contacts, location, headline, role/employer/dates, booking API, education and both skills. Skills share a multiline bullet; project information repeats in Experience and Projects. The letter is structurally complete and readable, but brief and generic: one paragraph summarizes background/work/education, followed by a short skills sentence. It offers little employer-specific argument or persuasive tailoring. This is not a polished-letter or general-readiness guarantee. Redaction limits exhaustive exact-prose assessment.

## Usage and cost

870 input tokens; 1,451 output; 0 reasoning; 2,321 total. Usage-based estimate: $0.0031195 at $0.25/M uncached input and $2/M output. Actual billed cost remains unknown; account billing/cache discounts unverified.

No documents were applied, approved or sent. The live-gate variable was restored to its previous presence/value in finally. Stopped after one request. No automatic rerun, production-default changes, reset, restore, push, deployment or Jira changes. Prior evidence and unrelated work preserved.
