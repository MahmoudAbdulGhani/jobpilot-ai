# User-approved email applications

From a saved job, approve a pack in the existing pack editor, then use **Apply by email**. Select the specific approved version and a connected sending mailbox. Enter the recruitment address twice and record where it came from. JobPilot never guesses a recipient, extracts one for sending, or fetches the supplied source URL.

**Prepare email review** creates an immutable snapshot, without sending. Review the displayed sender, recipient/source, subject and plain-text body. Download both exact PDF attachments; their sizes and SHA-256 fingerprints are shown. Check the confirmation and select **Confirm and send application** to approve and dispatch that snapshot. Cancelling a review before editing invalidates it. Preparing another review cancels the prior unsent review. A changed snapshot requires new approval; the send endpoint cannot accept content overrides.

PDF is the attachment format in this milestone: one CV and one cover letter from the chosen approved pack version. Each attachment is limited to 5 MiB and the complete MIME message to 15 MiB as local safety limits. Subject/address control characters and multiple recipients are rejected. No CC/BCC, sender aliases, arbitrary uploads, HTML body or tracking pixels are supported. Existing pack evidence/completeness checks and explicit pack approval are unchanged.

## Dispatch and reliability

The separate `EmailSender` interface implements Google's documented [MIME/base64url sending contract](https://developers.google.com/workspace/gmail/api/guides/sending) using `POST https://gmail.googleapis.com/gmail/v1/users/me/messages/send`. The [method reference](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send) permits `gmail.send`; reading scope is not needed. HTTP 200 with a valid message identifier is recorded as provider acceptance, **not recipient delivery or reading**.

Owner-scoped checks cover the job, approved pack version, mailbox and attempt. Before dispatch the server rechecks approval, exact selected pack content, mailbox identity/local capability and refreshed Google scopes. It refreshes OAuth credentials, not inbox content. Owner/job/pack locks serialize disconnect and source changes with dispatch. Revoked or missing send permission prevents dispatch. Refresh or configuration failure is reported as a preflight failure.

Persisted states:

| State | Meaning and allowed action |
| --- | --- |
| `review` | Immutable preview, not approved or dispatched. Cancel to edit or explicitly confirm Send. |
| `queued` | Approval recorded; dispatch has not yet been claimed. A repeated explicit send of this same snapshot can claim it. No background scheduler or automatic retry exists. |
| `sending` | A durable single dispatch claim exists. Repeated requests only return status. |
| `sent` | Gmail returned acceptance and a message ID. Application tracking is created as Applied; delivery/read status is unknown. |
| `failed` | Preflight prevented dispatch or Gmail returned a definite rejection. The stage and available HTTP status are recorded. No automatic retry. |
| `unknown` | Transport failure, ambiguous provider result or missing success ID. Delivery might have occurred; resend is blocked. |
| `simulated` | Guarded test provider accepted synthetic bytes; no real email and **no submitted tracking record**. |
| `cancelled` | Previous review invalidated; its Send request cannot dispatch. |

Database uniqueness allows only one active/accepted/uncertain attempt per owner/job. Repeated clicks, concurrent requests and separate browser tabs cannot dispatch the same attempt twice. The MIME Message-ID is stable, but it is **not** treated as Gmail deduplication or an exactly-once delivery guarantee. A crash after recording the dispatch claim leaves a blocked attempt; after two minutes the UI/API conservatively display unknown. The stored claim is never automatically reclaimed. A lost browser response prompts a status lookup, not a second send.

The adapter does not retry any send. It classifies documented client-error statuses as rejection and conservatively treats server/network errors as unknown, departing from Google's generic [retry advice](https://developers.google.com/workspace/gmail/api/guides/handle-errors) because blindly retrying a non-idempotent send risks duplicates. Check Gmail manually after uncertainty. Optional [reply synchronization](reply-synchronization.md) now supports separately consented, user-triggered exact Sent-message reconciliation. There is still no automatic polling or unknown-outcome override/resend mechanism.

Only confirmed real provider acceptance creates the tracking record and Applied event, with the selected CV/letter snapshot. Existing manual application records block sending rather than being overwritten. Any concurrent tracking conflict preserves the existing record and reports acceptance with a tracking warning. Once sent, use the tracking link to view/update the application; existing tracking form edits are not automatically overwritten. Follow-up emails and multiple submissions for a job are intentionally blocked. Failed attempts can be followed only by a newly prepared and explicitly approved review.

## Persistence and privacy

Additive migration **`c4d5e6f7a8b9`**, after `b3c4d5e6f7a8`, creates `email_applications`. A database trigger prevents changes to snapshot bytes, metadata, ownership and recorded approval. Status/result fields remain mutable. Approval binds the complete MIME bytes and snapshot metadata, including recipient source and attachment hashes. Attachments are rendered once and sent from the retained bytes; sending never rerenders documents.

Snapshots contain private message/document content in the application database and must be protected by its access controls and backups. OAuth credentials remain encrypted through the mailbox foundation; they are never included in snapshots or API results. Routine logs record no MIME, headers, attachment contents, tokens or unrestricted provider errors. SQL parameter values are hidden in the application engine's diagnostics. Keep HTTP/proxy body and authorization-header logging disabled as documented in the mailbox setup guide. Downloads are authenticated, owner-scoped, `no-store`, and served as attachments.

Deleting a pack later does not alter an existing attempt's snapshot. Deleting the owning job or user removes its email attempt records via existing ownership deletion semantics; this cannot recall mail or cancel an already dispatched message. Do not use deletion to resolve an unknown outcome or bypass duplicate protection. This is a private application history, not a permanent compliance archive.

## Google setup and blockers

Follow [mailbox setup](mailbox-connections.md): enable Gmail API, configure the consent screen/audience/test users, create a Web OAuth client with the exact backend callback, and privately set client ID/secret, callback, Settings return URL and a stable encryption key. Empty placeholders already exist in `.env.example`; no existing secret was changed. Connect with **Allow sending applications** and review Google's consent. `gmail.readonly` is unnecessary for this workflow.

`gmail.send` is a sensitive scope. Public external use generally requires verification unless an applicable exception is established. Demonstrate this explicit review/send workflow in the verification submission and accurately describe data handling in the privacy policy. Restricted reading requirements still apply only if separately enabling that capability. No publishing or verification approval is claimed.

The required local Google configuration is absent. Live OAuth, Google token refresh, Gmail acceptance and actual delivery therefore remain **unverified**. No real email, inbox, live AI or application-sending operation was used during implementation.

## Offline and guarded verification

Backend tests exercise mocked OAuth/Gmail, actual MIME serialization, exact attachment-byte equality, owner/job/pack isolation, approval invalidation, database immutability, missing/revoked permissions, repeated/concurrent submission, definite rejection, timeout and crash uncertainty, tracking and synthetic-mode guards. Existing mailbox, tracking and export regressions remain included. They use transaction rollback or clean up only newly created synthetic users; no reset, downgrade or truncation.

The connected browser scenario uses actual application APIs, pack approval and PDF rendering with the existing guarded synthetic providers. It selects the approved version, enters/confirms the recipient and source, downloads both attachments and checks their fingerprints, explicitly confirms send, then verifies **simulated**, no submitted record, and safe repeated submission. This verifies integration, not live Gmail.

Commands from repository root (PowerShell):

```powershell
$env:JOBPILOT_ALLOW_DESTRUCTIVE_TESTS='0'
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_email_applications.py backend/tests/test_mailboxes.py backend/tests/test_application_tracking.py backend/tests/test_pack_export.py -o addopts= -q
```

From `frontend`:

```powershell
npx vitest run tests/email-application.test.tsx tests/mailbox-settings.test.tsx
npx tsc --noEmit
npx eslint components/EmailApplication.tsx components/MailboxSettings.tsx tests/email-application.test.tsx tests/e2e/email-applications.spec.ts
npx playwright test tests/e2e/email-applications.spec.ts --workers=1
```

The additive revision was applied to local development and persistent test databases with all 16 pre-existing table row counts unchanged across the migration. No destructive migration test was run.

Verification result: 71 affected backend checks passed; after refining safe preflight failure categories, all 36 email checks passed again. Fifteen frontend component checks, TypeScript, targeted ESLint and the connected browser scenario passed. Existing Starlette deprecation and Windows development-server file-watcher/color warnings remain. All send responses were mocked or explicitly synthetic; live acceptance/delivery remains unverified.
