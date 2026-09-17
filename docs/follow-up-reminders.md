# Application follow-up reminders

One in-app reminder is available for each owned application. Open a saved job,
record an application, then use **Follow-up reminder** to create or edit its due
date/time and IANA timezone. Snooze explicitly moves it later and into the future;
complete and cancel retain the due date and timezone for reference. Editing or
snoozing a completed/cancelled reminder explicitly reactivates it. There is no
recurring schedule or separate reminder history in this milestone.

The **Reminders** view separates overdue/due-now, upcoming, completed and cancelled
items and links to saved-job application details. The signed-in shell checks due
reminders on mount, focus, local reminder changes, and once per minute while mounted.
These are reads from JobPilot's database, not mailbox scans. No background worker,
closed-app notifications, automatic sending or AI drafting is provided.

## Ownership, dates and duplicate protection

- `GET /api/reminders?view=overdue&limit=20&after=<application UUID>` is owner-scoped,
  capped at 100 results, ordered by immutable application UUID with an exclusive
  keyset cursor. Deletions cannot shift an offset or repeat a previous page. This
  is a live view, not a historical snapshot: edits and newly due items can change
  membership, so reload to see current results.
- `GET /api/applications/{id}/reminder` returns the existing lifecycle or `none`.
- `POST /api/applications/{id}/reminder` takes `action` (`create`, `edit`, `snooze`,
  `complete`, `cancel`) and the last `revision`. Scheduling takes `local_time`
  without an offset, `timezone`, optional `fold` (0 = first occurrence, 1 = second),
  and `confirm_terminal` when applicable. Unexpected fields are rejected.
- Dates are converted to UTC for storage/comparison and displayed in the selected
  timezone. Missing clock times at a daylight-saving transition are rejected;
  repeated times require an explicit occurrence. Due means `due_at <= now`.
  `tzdata` is an explicit dependency for Windows timezone support.
- The existing `applications.follow_up_date` is reused. Legacy non-null dates are
  active reminders displayed as UTC without rewriting their stored instants. New
  reminders default the form to the browser timezone; there is no global timezone
  preference. Legacy API date writes now require an explicit UTC offset. Once
  managed through reminder controls, differing legacy date writes are rejected.
- A row lock serializes reminder mutations; a revision rejects stale edits.
  Repeated or concurrent creation returns the existing lifecycle without changing
  it, even after completion/cancellation. The application row itself supplies the
  one-reminder uniqueness boundary; no duplicate reminder rows can be created.
- Rejected, withdrawn and accepted applications require explicit scheduling
  confirmation. `Accepted` is now an explicit tracking status; existing `Offer`
  also receives a conservative warning. Legacy scheduling cannot bypass this.
- Deleting an application deletes its reminder because all reminder fields live
  on that row. Existing saved-job/user cascades have the same cleanup behavior.

## Reply warning

The warning **Reply received — review before following up** derives from current,
owner-scoped confirmed reply associations for the saved job (`reply_headers` or
`user_confirmed`). Uncertain and dismissed matches do not trigger it. A correction
to another job moves the warning; dismissal removes it when no other confirmed
reply remains. Any retained confirmed reply for the job warrants review, including
one received before the reminder was created. Neither sync nor this warning changes
the reminder lifecycle or application status. The detail panel refreshes after
local sync/correction and on window focus; page reload also reads current data.

## Migration and preservation

Additive migration **`e6f7a8b9c0d1`**, after `d5e6f7a8b9c0`, adds nullable
`reminder_status`, nullable `reminder_timezone`, and `reminder_revision` default 0
to `applications`. It creates no replacement tables and rewrites no existing
application fields. Applied to development and persistent test databases using
only Alembic upgrade. Before/after row counts and whole-row fingerprints excluding
the three new columns matched for all **19 existing tables in each database**.
This is preservation evidence for this migration, not a recovery claim about
earlier incidents. No downgrade/reset/truncation was run.

Backend tests use transaction rollback; the existing concurrency tests and guarded
browser harness clean up only their newly created synthetic users. Unrelated files
and private `.env` values were not changed. No new credentials are required.

## Verification and remaining setup

Affected backend checks cover ownership, lifecycle, repeated creation, stale edits,
due-time equality, UTC date boundaries, both daylight-saving transitions, terminal
status confirmation, legacy API guards, keyset pagination, confirmed versus
uncertain replies, and deletion. Tracking, email sending and reply-sync regressions
remain provider-mocked. Frontend tests cover loading, empty/error/retry, explicit
timezone/confirmation, pending controls and reply/due warnings. Guarded browser
scenarios cover create → reload → snooze → complete and the existing tracking
record → reminder → status edit → delete flow.

Checks from `backend`:

```powershell
$env:JOBPILOT_ALLOW_DESTRUCTIVE_TESTS='0'
.venv/Scripts/python.exe -m pytest tests/test_reminders.py tests/test_application_tracking.py tests/test_reply_sync.py tests/test_email_applications.py -o addopts= -q
```

Checks from `frontend`:

```powershell
npx vitest run tests/reminders.test.tsx tests/reply-timeline.test.tsx tests/email-application.test.tsx
npx tsc --noEmit
npx playwright test tests/e2e/reminders.spec.ts tests/e2e/career-journal.spec.ts --grep 'reminder create|connected application tracking' --workers=1
```

82 affected backend tests, 18 frontend tests and both guarded browser scenarios
passed. TypeScript and targeted ESLint passed. Existing Starlette deprecation and
Windows Watchpack warnings remain. Destructive migration coverage was not run.

No live Google access, sending or AI calls were made. Real reply flags still depend
on separately enabled reply tracking and explicitly requested synchronization.
Existing [Google setup/consent/verification blockers](mailbox-connections.md#google-setup-not-performed)
and [restricted-scope/live-verification limitations](reply-synchronization.md)
remain: configure the client ID/secret, exact callback and Settings URLs, stable
encryption key, test users and required Google publishing approvals, then perform
separately authorized live verification. This milestone does not resolve those
blockers or claim live inbox verification.
