# Review and save the resume profile

The resume page shows all ten profile categories. Checked AI suggestions and edited
manual fields are submitted together. Manual controls start with the saved profile;
untouched fields are omitted from the request. Missing or rejected AI categories
remain visible for manual entry and are never invented from unsupported evidence.
CV work history is shown as separate editable role cards with evidence. Editing an
AI role changes its origin to user-provided; an added role can be saved alongside
untouched AI roles.

1. Choose or edit suggestions and enter any manual details.
2. Select **Review profile changes** to compare the saved and proposed values.
3. Select **Save profile changes** to commit the reviewed form.

A profile edit after AI generation does not require another AI call. A concurrent
edit after review requires reviewing again. Source text changes still require fresh
suggestions. On any failure, the form retains edits and selections.

## API

`POST /api/profile-suggestions/{id}/review` is owner-scoped and read-only. Its body
contains `selections`, optional `manual_fields` (a partial candidate profile), and
optional `manual_experience_entries` (additional or edited Experience entries).
At least one selected suggestion, explicitly supplied manual field, or manual
Experience entry is required.
It returns `current_profile`, `proposed_profile`, `changed_fields`, and the exact
`reviewed_profile_revision` to send back when saving.

`POST /api/profile-suggestions/{id}/apply` accepts the same body plus
`reviewed_profile_revision`. Legacy clients omitting that revision retain their
original generation-revision check. The server locks writes for the owner, checks
source freshness and the expected profile revision, validates the merged profile,
and commits the profile, provenance, and applied history together. Retrying the same
accepted selections and manual fields is idempotent; changing an already-applied
request returns 409. Manual Experience entries are included in the retry hash.

AI list entries append with duplicate suppression. Manual fields replace only the
explicitly provided fields, so arrays include their intended complete contents.
Explicit null clears a nullable field; omission preserves it. Selecting AI and
manual replacements for the same field returns 422; `manual_experience_entries`
can accompany selected AI Experience entries. Combined limits and invalid values
return field-specific errors without partial writes.

During an explicitly requested generation, a missing Experience suggestion triggers
one focused extraction pass over the professional work-history section. The server
accepts multiple quotes for one role only when they belong to the same contiguous
role block. The section stops before Projects; a failed focused pass leaves the
other supported categories available for review.

Suggestion responses include `field_statuses` for all ten fields: `suggested`,
`not_found`, or `needs_review`. This is derived for old records as well. Applied
history contains accepted suggestions and manual changes; rendering uses accepted
values rather than reverting to the original AI proposals. No schema migration is
needed.

## Regression coverage

Backend suites check stale review recovery, source freshness, ownership, all ten
persisted fields, manual-only updates, intentional clearing, duplicate suppression,
limits, invalid evidence, and idempotence. The browser test
`frontend/tests/e2e/profile-review.spec.ts` uses a synthetic account and an actual
local PostgreSQL database. It verifies that review writes nothing, rejects a
concurrent change, saves after another review, compares all ten fields through an
independent database connection and profile GET, and reloads both pages.

The browser fixture helper only accepts the local `jobpilot_test` target and the
test's synthetic account prefix. Account creation and cleanup use the guarded E2E
API. No production profile is written as part of these tests.
