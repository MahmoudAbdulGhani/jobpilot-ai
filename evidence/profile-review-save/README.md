# Complete profile review and save verification

Verified 2026-09-24.

## Result

The resume page now reviews selected AI suggestions and edited manual fields
together, then saves the complete accepted form in one database transaction.
Existing suggestions can be reviewed against a newer profile without another AI
call. Unchanged manual fields are omitted, and saved manual values are hydrated
when the page opens. All ten categories remain visible, including missing headline
and experience sections. Errors retain the form and identify invalid fields.

The reported database record was inspected read-only: its suggestions remained
ready/unapplied and referenced a profile revision of `none`, while the profile had
subsequently been created. The old frontend fixes had also not been included in
the prior commit. This release includes the application changes, not only tests.

## Checks

- Backend profile suggestions, candidate profile, review, and provider wire-schema
  suites: **230 passed**. Final profile-locking follow-up: **40 passed**.
- Frontend resume library, combined profile panel, profile, and API suites:
  **43 passed**.
- Real browser scenarios: **3 passed** across the targeted runs (combined profile
  save, existing resume workflow, and owner isolation).
- TypeScript and targeted ESLint: passed. Production Next.js build: passed.

The combined browser test created a synthetic local account and suggestion set,
then saved manual profile fields after generation to reproduce the stale revision.
Review left database values unchanged. Another profile change between review and
save correctly returned 409; reviewing again saved successfully without generation.

All ten fields were compared against the Apply response, a subsequent profile GET,
and an independent PostgreSQL connection after commit. This included both education
entries, Arabic/native, English/professional, skills, manual experience, salary,
and preservation of preferences changed elsewhere. Both resume and profile pages
were reloaded and checked. Tests cleaned up only their synthetic accounts.

Backend cases also cover manual-only saves, explicit clearing, unchecked entries,
duplicate skills, field collisions, list limits, source freshness, ownership,
invalid evidence, and idempotent retries. Frontend cases retain manual edits if
regeneration introduces a competing suggestion for the same field.

## Release

The backend was committed and pushed first as `5f5ce3a`. The deployed Render review
endpoint changed from 404 to the expected unauthenticated 401, with readiness 200,
before releasing the new frontend. No schema migration or secret changes were
required. Personal application records were not modified by the verification.

For the existing profile, open the updated resume page, choose **Review profile
changes**, inspect the comparison, then **Save profile changes**.

Implementation/API notes: [profile review documentation](../../docs/profile-review.md).
