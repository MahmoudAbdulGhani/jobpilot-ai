# Backup and restore rehearsal procedure (documented; not executed)

This document specifies the rehearsal procedure for backup and restore. **No backup, copy,
restore or provider call related to persistent data was executed during this task**; this is a
procedure ready for a separately authorized rehearsal on a disposable, isolated target.

Immutables while a rehearsal is in progress: the current development/persistent database, the
private storage location, and any live-provider connected mailboxes/applications. The rehearsal
must not restore over them or send applications/emails.

## 1. Scope and inventory (read-only first)

1. Run the private-file inventory from `backend`:
   `python -m app.storage_inventory > ../storage/file-inventory.json`
   - Opens a read-only DB transaction; records UUID, size, SHA-256 and proposed object key per local
     file; counts unreferenced UUID files. Never contacts storage and never changes rows/files.
   - Keep the manifest private; it contains no filenames or CV text.
2. Record current state: Alembic revision (`alembic current`), application version/commit, number of
   rows per table that the backup must reproduce, mailbox encryption/signing key identifiers.
3. Review the manifest for missing files, symlinks, size mismatches and orphan counts before
   copying anything. Do not copy files that do not reconcile.

## 2. Backup rehearsal

Commands assume credentials come from a private passfile/keyring in the secret environment and
never from command history. All destinations are private and encrypted.

1. Database:
   - `pg_dump --format=custom --file=<backup-path> <target>` with TLS verification
     (`PGSSLMODE=verify-full`), the application role with read access, and the schema owner
     permission as needed. Confirm the dump succeeds and inspect that `alembic_version` contains the
     expected head `e2f3a4b5c6d7`.
2. Private objects:
   - Copy original byte streams (no upsert/re-compression) from the current private location to a
     separate encrypted backup location at exact keys (`resumes/<UUID>`).
3. Metadata: include manifest, application version, Alembic revision, ownership metadata and
   cryptographic-key recovery instructions in the backup set. Store mailbox/signing keys separately
   and access-controlled; losing the mailbox encryption key makes stored OAuth credentials unusable.
4. Verify the backup set: file counts and sizes, checksums (compare production SHA-256 to the
   restored copy), DB dump integrity (`pg_restore --list` or `pg_restore -l`), and that the copy
   contains no public/signed URLs or plaintext credentials.

### Boundaries
- Never backup by copying the live database file or by stopping services without authorization.
- Object bytes are NOT included in Supabase database backups; they need their own backup.
- No backup was created during this task.

## 3. Restore rehearsal on a disposable target only

Restore must go to a **new isolated target**, never over the current database, and never as an
"upgrade" of an existing deployment without a migration plan.

1. Provision a fresh target database and a fresh private bucket. Apply the same restrictive RLS/no
   anon grants posture as production (see `deploy/supabase-api-lockdown.sql`).
2. Restore the DB dump with `pg_restore` (schema-aware, no `--clean` against anything but the
   disposable target).
3. Restore object bytes at exact keys and verify every SHA-256 and size against the manifest; verify
   database references all resolve.
4. Boot the backend against the disposable target with test/explicit staging configuration (production
   guards still on, test providers on as needed, no real network sends). Run:
   - `/api/ready` returns healthy (DB reachable, Alembic head exact).
   - Owner-scoped upload/download/delete works; foreign-user and anon access denied.
   - Disposable accounts cannot reach plan grants they should not have (free default; no carried
     legacy/beta beyond what the restored data legitimately contains).
5. Verify reads only. Do not resend queued/unknown applications or replies after a point-in-time
   restore. Reconcile external sends/replies before any future real restore.

## 4. Cleanup ledger and rehearsal report

1. After review, delete the disposable target (DB, bucket, files) and the disposable accounts.
2. Record the rehearsal outcome in a private ledger: who ran it, when, what was restored, which
   checks passed/failed, and any discrepancies.
3. Account deletion follows the reauthenticated Settings flow plus the separately scheduled cleanup
   command; never delete a user row directly. The external restore-time deletion ledger is part of
   rollback readiness ([Account data controls](account-data.md)).

## 5. Exit criteria before a real restore

- At least one full restore rehearsal passed on a disposable target with matching hashes/counts.
- Backup set content verified (DB + objects + metadata + keys) within the target RPO/RTO.
- Operator approved the RPO/RTO, retention window and deletion ledger.
- A communication plan exists in case providers/registries are unavailable during the restore.

RPO/RTO, retention, alerts and the deletion ledger remain operator decisions; this task set no
backup schedule and performed no restore.