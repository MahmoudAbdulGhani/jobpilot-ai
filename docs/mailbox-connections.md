# Gmail connection foundation

This foundation connects a mailbox and manages consent and credentials. The OAuth interface has no mail operations. [User-approved email applications](email-applications.md) provide a separate send workflow; [reply synchronization](reply-synchronization.md) adds separately consented, explicitly triggered bounded reads. Connecting, refreshing credentials and opening Settings never send messages or scan an inbox. No watch or background polling is implemented. A capability grant is not application approval or a synchronization request.

## Google setup (not performed)

1. Create/select a Google Cloud project and enable the Gmail API. Configure Google Auth Platform **Branding**, **Audience**, **Data Access** and **Clients**. Choose Internal only for an eligible Workspace organization; otherwise use External and add explicit test users while in Testing.
2. Create an OAuth client of type **Web application**. Register the exact authorized redirect URI, including scheme, port and path. For the normal local backend this is `http://localhost:8000/api/mailboxes/oauth/callback`. The browser harness uses its own synthetic callback on port 8010 and never needs Google credentials.
3. Set these values in the ignored local `.env` or the deployment secret manager; `.env.example` intentionally contains only empty placeholders:

   | Setting | Value to supply |
   | --- | --- |
   | `JOBPILOT_GOOGLE_CLIENT_ID` | Web application's client ID |
   | `JOBPILOT_GOOGLE_CLIENT_SECRET` | Client secret; server only |
   | `JOBPILOT_GOOGLE_REDIRECT_URI` | Exact registered backend callback |
   | `JOBPILOT_MAILBOX_SETTINGS_URL` | Fixed frontend return URL, locally `http://localhost:3000/settings` |
   | `JOBPILOT_MAILBOX_ENCRYPTION_KEY` | Stable Fernet key, separate from the authentication secret |
   | `JOBPILOT_MAILBOX_TEST_PROVIDER` | Keep `false` outside the guarded browser harness |

   Generate the encryption key with `cryptography.fernet.Fernet.generate_key()` in a trusted local process, writing it directly into a protected secret store/file rather than terminal output, logs or chat. A Fernet key encodes 32 random bytes in URL-safe base64. Back it up securely; changing or losing it prevents decrypting existing credentials and requires reconnection. Automatic key rotation is not implemented. Never commit secret files.
4. Install backend dependencies, apply the additive migration with `python -m alembic upgrade head` from `backend`, and restart the backend. For deployment use HTTPS for both URLs, secure authentication cookies, a trusted same-site frontend/API configuration, and the existing CORS allowlist. Local HTTP is accepted only for loopback hosts outside production. Callback and Settings URLs cannot contain query strings, fragments or embedded credentials.
5. Sign in to JobPilot, open **Settings**, and connect identity only first. Only select sending or reading when enabling that capability. Google may issue partial grants; the UI reports only requested capabilities whose exact scopes were granted. A live consent, refresh and revocation check is still required with an authorized test account. No such check was performed for this milestone.

The local configuration check found the client ID, client secret, callback, Settings URL and encryption key absent. Existing private configuration was not modified or printed.

## Consent, verification and publishing

The initial request asks for `openid email`, offline access and consent. Optional `send` adds **`gmail.send` (sensitive)**; `read_replies` adds **`gmail.readonly` (restricted)**. Read-only Gmail permission covers the entire mailbox, not only application replies; Settings explicitly discloses this. Neither `gmail.modify` nor `mail.google.com` is requested. Incremental authorization can retain previously granted Google scopes. Removing a local capability does not remove the Google grant; disconnect/revoke first to remove that grant.

Public external use of sensitive/restricted scopes generally requires Google verification unless an applicable exception is established. Configure accurate branding, authorized/verified domains, a public homepage and privacy policy, scope justifications, and the demonstration Google requests. This foundation alone does not demonstrate completed sending/reply features and is not a claim of public verification readiness. Do not publish unsupported capability claims. Internal, personal and testing exceptions must be assessed against Google's actual rules, not assumed.

Restricted Gmail access is subject to additional permitted-use and data-handling requirements; server-side restricted-scope access can require an annual assessment by a Google-approved security assessor. Plan this before publishing the reading capability. External apps in Testing generally receive refresh tokens that expire after seven days when Gmail scopes are included; the identity-only scope subset has an exception. Revocation, token limits and other causes can also invalidate tokens. The application reports reconnection required without guessing the cause of `invalid_grant`.

Official references checked for this implementation:

- [Google web-server OAuth flow, incremental authorization, offline access and revocation](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Google OAuth Flow reference, including PKCE verifier support](https://googleapis.dev/python/google-auth-oauthlib/latest/reference/google_auth_oauthlib.flow.html) and [S256 PKCE protocol](https://developers.google.com/identity/protocols/oauth2/native-app)
- [OpenID Connect userinfo identity](https://developers.google.com/identity/openid-connect/reference)
- [Gmail scope classifications](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Restricted-scope verification, exceptions and security assessment](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- [OAuth token expiration and testing restrictions](https://developers.google.com/identity/protocols/oauth2)

## Security and behavior

`MailboxProvider` separates the Google HTTP adapter from persistence. Only fixed Google OAuth/userinfo endpoints are used; redirects and retries are disabled. PKCE uses S256 and a random verifier. Token exchange is server-side. Identity uses verified HTTPS userinfo and the stable Google `sub`, not an email-address match.

Each flow has random state, a ten-minute expiry, a hashed browser nonce in an HttpOnly SameSite=Lax cookie, and an authenticated initiating owner. State is atomically consumed before token exchange, including denied consent. A new flow invalidates the old one. The verifier is encrypted and cleared upon consumption. Disconnect invalidates pending owner flows, including exchanges in flight. The callback returns only a safe outcome to a fixed Settings URL.

Access and refresh credentials are Fernet encrypted with owner/connection context, and never returned in API responses or stored in browser storage. Safe provider error categories replace error bodies. Callback query strings are scrubbed before routing and from Uvicorn access logs. **Reverse proxies must also omit callback query strings**, and operators must not enable HTTP body/header debug logging. Encryption protects stored credentials, not a compromised application process with access to the encryption key.

All connection operations require owner-scoped access. A Google account is globally unique by provider/subject: another owner gets a generic unavailable result, and reconnect must use the existing account. Connecting an already listed account preserves its current settings; permission changes use that row's explicit reconnect control. Disconnected identity rows remain reserved to their original owner. Account transfer and deletion UI are not implemented.

An access-token expiry produces `expired` without network calls. **Check connection** explicitly refreshes OAuth credentials only. Invalid/revoked credentials produce `reconnect_required` and remove stored credentials; transient provider errors retain them. Listing connections cannot know about a remote revocation until a check is made. Disconnect deletes local credentials/capabilities and requests Google revocation. If revocation cannot be confirmed, `revoke_failed` tells the user to remove access in Google account connections; credentials are not retained for automatic retry. Revocation can affect the app's combined grants.

API surface: authenticated `GET /api/mailboxes`, `POST /api/mailboxes/oauth/start`, `POST /api/mailboxes/{id}/check`, and `POST /api/mailboxes/{id}/disconnect`; the state/cookie-bound callback is `GET /api/mailboxes/oauth/callback`.

## Migration and verification

Additive revision **`b3c4d5e6f7a8`**, after `a2b3c4d5e6f7`, creates `mailbox_connections` and `mailbox_oauth_states` with owner references and indexes. It was applied to the local development and persistent test databases. Counts in every pre-existing table were unchanged across this operation. No reset, downgrade or truncation was run.

Mocked verification:

- 87 affected backend tests passed (mailbox, database safety, configuration and authentication). Coverage includes owner isolation, duplicate accounts, exact scopes and PKCE exchange, replay/expiry/wrong browser, encrypted storage/context, refresh and partial grants, sanitized failures, disconnect and exchange races, and guarded test-provider access. Existing framework/test deprecation warnings remain.
- Seven Settings component tests passed; targeted ESLint and TypeScript checks passed.
- One connected Playwright scenario passed: sign in, identity-only connect, explicit send-permission upgrade, refresh, confirmed disconnect and reload. It uses actual application endpoints with the guarded synthetic provider; it checks that API/browser storage contain no provider credentials and cleans up only its own synthetic user.

The browser provider requires both `E2E_TEST_MODE` and the configured test database, uses an ephemeral harness encryption key, and cannot silently replace Google. This is **mocked OAuth verification, not live Google verification**. Existing persistent data and unrelated workspace files were preserved.
