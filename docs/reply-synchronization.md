# User-triggered Gmail reply tracking

In Settings, select **Enable reply tracking** and explicitly update/reconnect the mailbox to grant `gmail.readonly`. The consent copy explains that Google permits **mailbox-wide reading**, while JobPilot limits this feature to application threads. Sending permission stays separate. Connecting, reconnecting, opening Settings or loading a timeline never starts scanning.

From a saved job's **Application reply timeline**, choose **Sync replies (next bounded batch)**. This reads one bounded batch; there is no scheduler, watch subscription, background polling or automatic retry. **Refresh saved replies** reads JobPilot's database only. The read-provider interface has no send or attachment-download operation.

## Coverage and matching

Only threads identified by Gmail IDs retained from JobPilot sends are synchronized. Replies moved to another thread, applications sent outside JobPilot and oversized threads may need manual review in Gmail. No recruiter-address or subject search is used to discover or confirm replies.

The original provider message ID anchors the thread and its RFC Message-ID. An incoming message in that thread with `In-Reply-To` or `References` pointing to the original RFC ID is a confirmed association. Thread-only candidates are **uncertain**, even when their sender/subject looks similar. The original message, Sent messages, drafts, messages from the connected address and messages predating dispatch are excluded. Conversation matching is not authentication of a sender or proof of its claims.

Matched responses show **Reply received**, received time, sender, subject and a short Gmail text preview. Full bodies and attachment bytes are not downloaded. The preview can be truncated or absent. React renders it as escaped text without images, scripts, remote resources or automatic links. The provider field mask excludes raw MIME, payload bodies and MIME parts. Header data may arrive transiently, but only displayed fields and association identifiers are retained.

Uncertain candidates require **Confirm association** before linking. Users can correct a reply to another owned saved job or dismiss it. Resynchronization preserves these choices; a correction does not silently create a routing rule for future messages. Replies never automatically change Interview, Rejected, Offer or other statuses. Use the existing tracking form explicitly. Refreshing tracking is also explicit so unsaved form edits are not overwritten automatically.

## Bounds and progress

Each invocation allows one OAuth refresh and at most **8 Gmail read requests**, one history page (`maxResults=10`) and five candidate previews. Responses are capped at **256 KiB**, baseline/history pages at **200 message references**, previews at 2,000 characters, and sender/subject at 512 characters each. The read adapter uses five-second network timeouts; OAuth retains its ten-second timeout. No retries occur.

A baseline captures `getProfile(fields=historyId)` before reading the known thread's message IDs/labels. This avoids losing concurrent additions and avoids using an old thread's history ID as the current mailbox checkpoint. Pending IDs/page tokens and replies commit atomically. The checkpoint advances only after queued candidates and the final history page are processed; another click handles the next batch. Mailbox/message uniqueness prevents duplicates; saved or dismissed previews are not downloaded again. The timeline shows the 100 most recent matching replies and offers the 100 most recent owned jobs for corrections.

History responses can contain mailbox-wide **identifiers**. Unrelated thread IDs are discarded without fetching their messages or retaining their identifiers. A provider interruption leaves the remaining queue intact. A process interruption rolls back uncommitted changes, allowing a later explicit request to replay safely. Owner locks serialize concurrent sync, consent/disconnect and association corrections.

An expired history cursor (HTTP 404) resets progress. The next explicit click rebuilds **only the known application thread**, never a mailbox-wide rescan. Invalid page tokens restart the bounded history window with deduplication. Malformed/oversized responses stop without advancing the checkpoint. Threads above 200 references are outside the initial supported baseline size.

Rate limits persist a mailbox-wide cooldown across attempts: numeric Retry-After is bounded to 60–3,600 seconds, otherwise 60 seconds. The UI displays the wait; no automatic retry runs. Missing reading scope removes only the local reading capability. Invalid/revoked credentials require reconnecting. Safe error categories replace provider error bodies. Tokens, cursors, message content and unrestricted provider errors are not routine logs or diagnostics.

Disconnect serializes with a bounded batch. A batch already started can finish before disconnect returns; afterward credentials are removed and future batches are refused. No continuing worker remains.

## Unknown-send reconciliation

An unknown send, including an interrupted dispatch older than two minutes, is never resent. With explicit reading consent and Sync, JobPilot searches **Sent only** for its server-generated UUID RFC Message-ID, with `maxResults=2`. Reconciliation requires one result with no additional page, exact original Message-ID/sender/single recipient/subject/Date headers, the Gmail SENT label and no DRAFT label. Similarity, a reply referencing the ID, or multiple results are insufficient.

On success, Gmail message/thread IDs are retained and the attempt becomes sent with `reconciled_exact_original_in_sent`. A tracking record is created as Applied if absent; existing user-edited tracking/status is preserved. Recipient delivery and reading remain unknown. This is strong original-message identification, **not cryptographic re-verification of attachment contents**; no attachments are downloaded. The next separate Sync action retrieves replies. A rewritten RFC ID or inconclusive evidence leaves sending unknown. Synthetic providers never turn unknown sends into real acceptance.

## Retention and deletion

`mailbox_replies` stores relevant sender/subject/preview/time, provider/RFC identifiers, source attempt and association. `reply_syncs` stores bounded pending IDs/checkpoints and safe status/cooldown data. Neither table stores unrelated messages, full bodies, attachments or OAuth credentials. Previews are owner-scoped private database data, not separately encrypted like OAuth tokens.

Disconnect preserves saved history and corrections. **Dismiss and erase preview** clears sender, subject, preview and RFC ID immediately; minimal provider-ID tombstones remain to prevent re-import. Deleting the source job/attempt, mailbox row or owner cascades to its reply/sync rows. Deleting a destination job clears its association. Corrected replies still depend on their original source attempt for deletion. Gmail-side deletion is not mirrored: this version consumes additions only. Backups follow the deployment's retention policy.

## Google setup and official documentation

Follow [mailbox setup](mailbox-connections.md): enable Gmail API, configure the OAuth Web client and test audience, register the exact callback, and privately supply the client ID/secret, callback, fixed Settings URL and stable encryption key. All five remain absent locally. No secrets or private configuration were changed. No new environment setting is needed.

`gmail.readonly` is restricted. Public external use generally requires restricted-scope verification unless an applicable exception is established; server-side access can require a Google-approved security assessment. Complete permitted-use justification, privacy/deletion disclosures, domain/brand verification and the requested demonstration before publishing. No approval or general production readiness is claimed.

Official references checked:

- [Sync and expired history](https://developers.google.com/workspace/gmail/api/guides/sync)
- [History pagination and messageAdded records](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list)
- [Known-thread metadata](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get)
- [Message retrieval](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get)
- [Bounded message search](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)
- [Current history checkpoint](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile)
- [Gmail errors/rate limits](https://developers.google.com/workspace/gmail/api/guides/handle-errors)
- [Restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)

## Migration and checks

Additive **`d5e6f7a8b9c0`** follows `c4d5e6f7a8b9`, creating only the two reply tables and indexes. It was applied to development and persistent test databases; all **17 pre-existing table row counts stayed unchanged**. No reset, downgrade or truncation was run. Tests roll back their data or clean up only newly created synthetic users.

**86 affected backend tests passed**, followed by **32 reply tests** after adding malformed-page, unrelated-history, oversized-thread and preserved-tracking regressions. **20 frontend checks**, TypeScript and targeted ESLint passed. The guarded browser scenario passed: sending-only operation → separate read consent → no scan on connect → sync → reply timeline → association correction → explicit status update. Existing Starlette and Windows development-server warnings remain.

From repository root:

```powershell
$env:JOBPILOT_ALLOW_DESTRUCTIVE_TESTS='0'
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_reply_sync.py backend/tests/test_mailboxes.py backend/tests/test_email_applications.py backend/tests/test_application_tracking.py -o addopts= -q
```

From `frontend`:

```powershell
npx vitest run tests/reply-timeline.test.tsx tests/mailbox-settings.test.tsx tests/email-application.test.tsx
npx tsc --noEmit
npx playwright test tests/e2e/email-applications.spec.ts --workers=1
```

All provider verification was mocked or explicitly synthetic. Live consent, field-mask behavior, history pagination/expiry, mailbox matching and real Sent reconciliation remain unverified. No live Google, email, AI, publishing or deployment operations were performed.
