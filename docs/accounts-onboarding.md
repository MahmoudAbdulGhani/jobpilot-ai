# Accounts, recovery and onboarding

Registration defaults to `JOBPILOT_REGISTRATION=invite-only`; `closed` refuses all new registrations, and `public` permits registration without an invitation. New registrations require email verification before login. Existing users remain active/verified with their original password and data. The existing owner bootstrap has no separate administrator role; no registration payload can assign roles or privileges. Administration remains a local CLI operation requiring trusted server/database access, never a public admin endpoint.

## Invitation administration

Configure `JOBPILOT_ACCOUNT_APP_URL` to the trusted frontend origin (HTTPS in production; localhost HTTP permitted only outside production). Never derive links from request Host, forwarded headers or submitted URLs. From `backend`:

```powershell
.venv/Scripts/python.exe -m app.cli invite --email person@example.com --hours 24 --output C:\private-operator-directory\invitation.txt
```

The command creates exactly one email-bound, single-use invitation, expiring in 1–168 hours. It refuses to overwrite an output file. Use an operator-private directory; on Windows restrict its ACL to the operator before running the command. The invitation is a bearer secret: share privately and delete the local file after handoff. It is never printed or logged. Only its SHA-256 hash is persisted. Invitations are not automatically emailed. `setup-owner` remains a one-time operation and cannot replace an existing owner. Registration/email locks and row locks serialize acceptance; a second acceptance fails.

## Transactional email

Set the empty placeholders in `.env.example` in an untracked secret store/environment:

- `JOBPILOT_ACCOUNT_MAIL_TRANSPORT=smtp`
- `JOBPILOT_ACCOUNT_SMTP_HOST`, port (default 465), user and password
- `JOBPILOT_ACCOUNT_MAIL_FROM` with an authorized sender address
- `JOBPILOT_ACCOUNT_APP_URL` with the trusted frontend base URL

This adapter uses certificate-validated implicit TLS, a 10-second socket timeout, no automatic retries, and checks SMTP recipient acceptance. It never uses connected Gmail mailboxes, OAuth scopes or application email snapshots. Configure your transactional provider's domain/sender verification, SPF/DKIM/DMARC and delivery/bounce monitoring separately. SMTP acceptance is not inbox delivery. Disabled/misconfigured transport returns an explicit 503; a rejection or timeout says acceptance was not confirmed. SMTP acceptance followed by a database commit failure can leave an unusable link: the user must request another email, not assume delivery or success.

Recovery and verification requests return the same message for known and unknown addresses. Both invoke the same transport; unknown/ineligible addresses receive a neutral account-request message without a token. This avoids making transport errors an account-existence oracle. Recipients may ignore unsolicited messages. Database-backed throttles limit each normalized address to 5 requests/hour and each direct client IP to 30/hour across account actions. Throttles use hashes, persist across workers and survive failed requests. Configure a trusted reverse proxy and upstream abuse limits before public launch; do not blindly trust client-supplied forwarding headers. Shared NAT users share the IP allowance.

Verification links expire after 24 hours; reset links after one hour. Tokens are single-use, stored only as hashes and consumed under database locks. Reset revokes refresh tokens, advances the user's access-token version and invalidates other outstanding reset links. Login is required afterward. Legacy JWTs without a version work only while the account version is zero. Email verification and reset tokens are purpose-bound; a reset is not a verification bypass. Passwords are 12–128 characters and hashed using existing Argon2 configuration. Tokens use URL fragments, are removed from the address bar, kept in component memory and submitted in POST bodies; no browser storage. Reopening the original email link is necessary after reloading a token screen. Account validation errors omit submitted input. Do not enable HTTP body logging or third-party analytics on account pages.

`test` transport is an in-memory sink requiring BOTH E2E mode and the dedicated test database; it sends nothing. Guarded browser fixture endpoints expose only random synthetic addresses created by that fixture, with an unguessable per-fixture ticket. There is no production email-inspection endpoint or console transport printing links. Unit tests inject a mock transport. Test-provider acceptance is not evidence of live email delivery.

## Onboarding and retention

New verified users enter `/onboarding`. Profile, CV upload/extracted-text review, and save/discover-job steps link to existing owner-scoped features. Each optional step can be marked done or skipped; the next step persists on the account. The navigation's Getting started link resumes it after visiting another feature. No Gmail connection, AI call or worker is required; disabled AI is disclosed. Existing users are marked `done` so their normal login destination remains saved jobs, but they can revisit the checklist.

Migration `a8b9c0d1e2f3` adds three user columns and token/throttle tables without removing existing data. The subsequent [account data controls](account-data.md) add password-reauthenticated export/deletion, a local recovery-account procedure and scheduled bounded retention for expired tokens, throttles and email previews. Configure that scheduler before sustained public operation. Expired/consumed tokens never become usable again. Password reset invalidates sessions and exports without deleting profile, CV, job or application data.

## Verification and launch dependencies

Verified locally on 2026-09-17: 55 affected backend checks (53 auth/account/CLI checks plus 2 final enumeration regressions), 3 frontend component checks, TypeScript, targeted ESLint, and one connected Playwright scenario covering invitation acceptance → verification → onboarding skip/reload → reset → new-password login. Concurrent invitation acceptance and reset consumption use two independent database sessions and clean up only their new synthetic users. The browser initially exposed a test navigation race (filling the old screen before navigation completed); waiting for the destination heading fixed the test. The final browser run passed. No full suite or destructive migration tests were run.

The additive upgrade was applied to development and persistent test databases. Before/after migration and post-test checks compared counts and original-field fingerprints for all 21 pre-existing tables in each database: identical. Existing user password hashes and original fields were included in that comparison. No resets, downgrades, truncation or live provider calls were used. Guarded browser fixtures leave only synthetic consumed invitation/throttle records in the new tables; existing data was not used as cleanup targets.

Current local presence-only configuration check: registration is invite-only, transactional transport is disabled, and the account application URL, SMTP host, sender, username and password are unconfigured. No secret values were printed or modified.

Only mocked transport and guarded browser verification are authorized. Live SMTP credentials/delivery, production HTTPS/proxy behavior and email-domain deliverability still require deployment setup and separately authorized verification. Existing Google consent/publishing/restricted-scope blockers remain documented in the mailbox documentation; Gmail is optional for onboarding.

Security design follows [OWASP's account recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) for purpose-bound single-use tokens, trusted URLs, generic responses and session invalidation. This is not a claim of a full security audit.
