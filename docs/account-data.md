# Account data controls

Settings offers password-reauthenticated private export and explicit account deletion. These controls are not a legal-compliance certification. Decide applicable retention, notices and legal obligations separately.

## Export

Voice interview exports also include unexpired transcript drafts and safe speech
dispatch metadata. Raw recordings and generated audio are never stored by
JobPilot. The retention command clears expired transcript drafts; dispatch
receipts remain until session/job/account deletion to preserve idempotency.
See [voice privacy and limits](voice-interview-practice.md).

The authenticated owner must supply their current password. Reauthentication attempts share a five-per-hour account limit with deletion. An export is downloadable only with the same active owner's session version, before its expiry (default ten minutes; configurable 1–10). Password reset invalidates outstanding downloads. Only one export per account is retained; creating another replaces it. No signed public URL, browser-stored credential or email delivery is used. The ZIP is stored privately as a bounded database byte field, not an ephemeral web-worker file. Scheduler delays cannot make an expired download usable.

`account.json` includes account identity, profile/provenance, saved jobs, applications/status history/reminders, packs and their versions, reviewed resume text, profile suggestions, fit results, interview snapshots/turns/usage, email application snapshots and attachment bytes (base64), retained replies and sync status. `documents/<resume UUID>` contains the original upload bytes; filename and extension are in the JSON. CVs/letters generated from structured blocks remain JSON; no new PDF/DOCX render or AI call occurs. Missing document bytes fail the export instead of silently omitting a file.

A reviewed allowlist excludes passwords, authentication token hashes, OAuth tokens/state/PKCE values, internal idempotency/lease keys, global rate-limit keys, duplicated raw email MIME, deleted/expired material, external provider records and historical backups. Future columns are not automatically included; schema changes must review both export coverage and ownership barriers. User-entered content may itself contain sensitive information; protect the downloaded archive.

Default limits: 25 MiB including ZIP overhead, 10,000 exported rows across all tables, 32 uploads, a 60-second assembly deadline checked between operations, and 15-second database statements. A single storage operation may run beyond the assembly deadline until its existing adapter timeout. The PostgreSQL preflight counts/sizes selected fields before transferring them. Exceeding a bound fails clearly; the operator must arrange a separately reviewed export for larger accounts. Peak memory can be several times the archive limit; concurrency is serialized per account, not globally. Size/pool/concurrency capacity needs staging load validation.

## Deletion and recovery

The owner supplies their password and types `DELETE MY ACCOUNT`. Acceptance atomically marks them inactive, increments session version, deletes refresh/account/OAuth-state tokens and temporary exports, and persists a content-free deletion receipt. Existing tokens stop authorizing requests immediately. The response clears auth cookies; the receipt is kept only in page memory and grants status lookup only, never account access. Closing that page requires operator assistance to check progress.

There is no web administrator role in this application. Administrative authority is local CLI/database operation. The last active verified account cannot delete itself while there is no other verified recovery login. A trusted local operator can run, from `backend`:

```sh
python -m app.cli create-recovery-account --confirm-local-recovery
```

This prompts for a new email/password without echoing the password and creates an ordinary verified login. Verify that login works before requesting the original account's deletion. It does not promote ordinary users or transfer local infrastructure authority. Do not bypass the guard with SQL or reactivate a pending deletion.

Every current owned table, including child document/version/event tables, has an additive PostgreSQL insert/update barrier that locks/checks its owner. It rejects writes for inactive accounts; required FK cascade actions still work. AI dispatch checks active status after its durable claim and cannot save a late result into an inactive/deleted account. Work claimed before acceptance can already be in flight and cannot reliably be recalled. Existing Gmail dispatch/sync owner locks serialize acceptance with those bounded operations. Authentication stops new work; reading permission is never added to send or delete.

Cleanup runs separately, never during connection or page load. Each invocation handles at most one account and 20 uploads, with a five-minute crash lease and 30-second database statements. Original file metadata is kept until storage confirms deletion; an interrupted DB transaction may require idempotently deleting already-removed objects again. Cascade deletion removes snapshots, packs/versions, interviews/results, applications/reminders, email MIME/attachments, mailbox credentials, user-linked tokens and owner/email-specific throttles. Shared IP throttles remain under retention; other users/global configuration are not removed.

Revocation is claimed durably before any external request, attempted once for at most the configured batch of mailbox connections, using the existing bounded provider adapter. Failure, a crash, missing configuration or additional connections sets an explicit **provider revocation unconfirmed** warning. No automatic provider retry occurs. Local data removal continues; Google grants, Gmail copies, recipients' mail and provider logs are outside JobPilot's deletion boundary. Users can remove grants through Google account connections. Previously dispatched email cannot be recalled.

Pending/failed cleanup is never reported complete. File/DB failures retain a retryable receipt and remaining metadata; rerun the scheduler after fixing configuration/storage. `complete` means local account content and known owned files have been removed; a minimal receipt (UUIDs, hashed receipt secret, status, timestamps and revocation outcome) remains temporarily. Existing unreferenced storage orphans cannot reliably be attributed to an account: investigate the private storage inventory before launch. This implementation does not claim to identify/delete unknown historical orphans.

## Scheduling and retention

From `backend`, with the configured server environment (no secrets in shell arguments):

```sh
python -m app.account_cleanup --dry-run
# FUTURE OPERATOR ACTION: mutates eligible data and can revoke Google tokens.
python -m app.account_cleanup --execute --batch-size 20
```

Omitting `--execute` is read-only. Output contains eligible counts and safe status categories, never record content or credentials. Schedule the execute command once per minute; repeat batches until counts drain, alert on failed/pending accounts and nonzero command exits. Without that scheduler physical cleanup does not happen. Multiple invocations use row locks and crash leases; the command does not start background workers in web processes. Never run it against a persistent development/test database merely to verify cleanup; tests use only synthetic records and mocked providers.

| Setting | Default | Effect |
|---|---:|---|
| `ACCOUNT_EXPORT_MINUTES` | 10 | Download expiry and eligible archive purge |
| `ACCOUNT_EXPORT_MAX_MIB` / `ACCOUNT_EXPORT_MAX_ROWS` | 25 / 10000 | Export resource ceilings |
| `ACCOUNT_TOKEN_RETENTION_DAYS` | 1 | Purge OAuth/account/refresh tokens this long after expiry |
| `ACCOUNT_OPERATION_RETENTION_DAYS` | 30 | Purge old throttle windows and completed deletion receipts |
| `ACCOUNT_EMAIL_PREVIEW_DAYS` | 90 | Clear retained reply preview text at the received-time cutoff |

Expiry comparisons are inclusive, UTC-aware. Preview expiry preserves sender, subject, identifiers, dates and association so tracking and deduplication continue. It does not delete sent message snapshots or attachments. Those and AI histories remain until their ordinary feature deletion or account deletion; active idempotency/dispatch records are not age-purged because that could permit duplicate sends/calls. Pending/failed deletion receipts do not expire automatically. Platform operational logs are outside this DB command: configure a bounded host retention policy separately (proposed 30 days, not claimed configured).

## Backups and launch dependencies

Deletion is not immediate erasure from historical backups. Follow the deployment runbook's proposed daily database **and object-byte** backups with 30-day encrypted retention, subject to operator approval/provider capabilities. Before restoring an isolated backup, apply a separately protected deletion ledger covering at least the oldest restorable backup, suppress deleted accounts/files, and verify ownership before traffic. The short-lived application receipt is not a durable cross-backup deletion ledger. That external ledger, backup expiry, encryption/access policies and a restore drill remain launch blockers; none was implemented or tested against a live backup here. Restoring an old backup without suppression can resurrect deleted data.

Google setup/consent/verification and restricted-scope dependencies remain as documented in mailbox setup. SMTP and AI are not needed for export/deletion acceptance. Live revocation/private object deletion, scheduler deployment, storage orphan reconciliation and load testing remain unverified. No live providers, emails or AI were used for this milestone.

Migration `b9c0d1e2f3a4` adds export/receipt tables and ownership triggers without changing existing rows; it is forward-only. Use the existing single release migration procedure, never per-worker upgrades or a downgrade/reset.

## Verification record

241 affected backend checks passed, including 14 account-data tests. Coverage includes owner isolation, immediate password reauthentication and throttling, export expiry/session-version invalidation, exact upload bytes and secret exclusions, archive bounds and missing storage, complete ownership cascades, storage failure/resumption, revocation failure/crash lease, rejected inactive-owner writes, a mocked interview finishing during deletion, the last-account guard, UTC retention cutoffs and preview/header preservation. Revocation and storage calls were mocked; no real account or file was removed.

13 frontend checks passed; TypeScript and targeted ESLint checks passed. The connected guarded browser scenario passed export download → explicit deletion → denied login → pending receipt. Completed/failed cleanup is verified through backend tests; the browser does not execute the destructive cleanup scheduler or live provider revocation. The development cleanup command was exercised only in dry-run mode, reporting zero eligible records. Migration downgrade/reset coverage was deliberately not run.

Before/after read-only counts and full-row fingerprints cover the 24 preexisting tables in development and persistent test databases. Preexisting rows were unchanged; the Alembic revision advanced and two empty tables were added. The test throttle table gained one transient record from the first browser run; excluding that one row reproduces the exact original count/fingerprint of its four preexisting records. No preexisting throttle was removed. Browser-fixture cleanup now removes its own account-specific throttle keys. This residual operational hash follows the configured retention policy; it is not an existing account/file loss. Actual backup restoration, large-account load tests, production scheduler operation and live Google/private-storage deletion remain unverified.
