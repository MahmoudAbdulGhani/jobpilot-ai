# Optional voice interview practice

Voice is an input/playback layer on existing private text interviews. It does not
change interview, profile, fit or pack models, prompts or evidence validation.
Enable voice controls inside a session, explicitly start the microphone, stop,
play back or cancel, then consent and send for transcription. Review/edit the
transcript and choose **Use reviewed transcript as answer draft**. Only the
existing Save/Submit buttons persist/evaluate that answer. Transcription never
advances a session. Assessments use submitted text, not accent, personality,
emotion, honesty or employability. Recognition errors can still affect a draft;
review is essential, especially for names, dialects and technical terminology.

Optional question audio is clearly labelled AI-generated. Generation and Play
are separate actions; visible text, stop, mute and normal audio controls remain.
The server selects the current question and displayed source excerpt, rather than
accepting arbitrary speech text. The excerpt may quote the job description or a
previous submitted answer; the consent notice explains this. No full CV, profile
or mailbox content is included in TTS.

## Configuration and official contract

Speech is disabled by default. Set `JOBPILOT_VOICE_ENABLED=true` and configure
`JOBPILOT_VOICE_API_KEY` in the backend secret manager (or untracked local `.env`).
The dedicated key may belong to the same OpenAI project; it is never returned to
the browser. No existing key or production default was changed by this milestone.
Missing speech configuration disables only voice. Models are explicitly
allowlisted: `JOBPILOT_VOICE_TRANSCRIPTION_MODEL=whisper-1` and
`JOBPILOT_VOICE_SPEECH_MODEL=tts-1`, provider `openai`, built-in voice `alloy`.
These documented models provide predictable duration/character estimates for a
bounded transcription-and-question-playback task. No custom voice or voice cloning.

Official documentation checked 2026-09-17:

- [File transcription](https://developers.openai.com/api/docs/guides/speech-to-text):
  `/v1/audio/transcriptions`, Whisper JSON transcript, up to 25 MB provider upload.
  The provider accepts several formats, but **JobPilot intentionally accepts only
  canonical mono 16 kHz signed 16-bit PCM WAV**. Header, declared lengths, PCM
  parameters and actual byte length are validated, regardless of browser MIME.
- [Whisper model and pricing](https://developers.openai.com/api/docs/models/whisper-1):
  USD 0.006/minute. Whisper supports multilingual recognition; the transcription
  guide links its 98-language list. No translation is requested. English, Arabic
  and French are among supported languages; dialect/technical accuracy is not
  established by these mocked tests. Language detection is left to the provider.
- [Speech API](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create):
  `/v1/audio/speech`, `tts-1`, `alloy`, MP3; documented input limit 4,096 characters.
- [TTS-1 pricing](https://developers.openai.com/api/docs/models/tts-1): USD 15 per
  million input characters. [Speech guide](https://developers.openai.com/api/docs/guides/text-to-speech)
  describes multilingual speech, including Arabic/French/English, with voices
  optimized for English, and requires disclosure of generated speech.

JobPilot is stricter: default/hard maximum 60 seconds (configurable downward),
minimum 0.25 seconds, at most 1,920,044 upload bytes, 15-second upload deadline,
3,000 transcript characters, 600 question characters, 1 MB generated audio and
30-second provider timeout (configurable up to 60). Duration comes from validated
PCM samples, never a client-supplied duration. The browser also caps capture and
stops/discards active recording when the tab is hidden or controls unmount.
There is no background recording, listening, streaming interview or worker.

HTTPS or localhost and microphone/Web Audio support are needed. This initial
recorder uses the browser's ScriptProcessor compatibility API; it is deprecated
and not universally supported. Unsupported/denied/interrupted capture retains
text and offers the text alternative. Browser mobile suspension and real device
compatibility remain live/manual verification items. Do not promise background
operation. Silence or noise may produce inaccurate text; nothing is auto-submitted.

## Quotas, failures and privacy

Every dispatched speech request consumes the existing per-account AI request
budget, including failures; the shared in-flight gate prevents overlapping paid
work. Additionally, default 18 requests per session (hard configuration maximum
30). Account quota is not refunded by deleting sessions. No retry or provider
fallback occurs. UI click guards plus owner/request-key uniqueness and a durable
pre-dispatch claim deduplicate repeated/concurrent requests. A key cannot be reused
for changed content. Failed keys are not re-dispatched; recording again is an
explicit new bounded request. Stale pending receipts are shown as unknown.

Raw recordings are read through a capped raw request stream, not multipart
`UploadFile`, avoiding disk spooling. The provider receives bytes in memory.
Generated speech is bounded in memory and returned once; it is not persisted.
Repeat successful TTS requests return the receipt without audio and do not charge
again. Playback survives only within the current mounted controls. No audio
temporary files exist to sweep after process interruption. Request/client buffers
are released/closed on completion/failure; a timeout worker may retain its input
until its bounded network call exits, but cannot write application data. Process
termination releases memory; this is not a cryptographic memory-erasure guarantee.
Configure reverse proxies without body logging, disk request buffering or body
capture for voice endpoints; application guarantees do not configure an external
proxy, crash-dump collector or provider retention.

Transcript drafts are private, retained for 10 minutes by default (configurable
1–60); expired drafts are inaccessible via replay/export. Schedule the existing
`python -m app.account_cleanup --dry-run` / maintenance command as documented in
[account data](account-data.md) to physically clear expired drafts. Dispatch
metadata/idempotency receipts remain until the session/job/account is deleted so
cleanup cannot cause a repeated charge. Exports include unexpired transcript
drafts, safe configuration/usage and receipts, excluding request hashes/keys and
audio. Saved reviewed answers retain existing interview snapshot semantics.
Session/job/account cascade deletion removes speech receipts/drafts; inactive-owner
write barriers and post-call ownership checks prevent late data resurrection.
Backups and external provider retention follow their own policies, not immediate
JobPilot deletion. Provider usage/billing remain unknown when not supplied; local
duration/character cost estimates are explicitly estimates. Routine logs contain
neither audio, transcripts, provider bodies nor credentials.

## Verification and a future live plan

Mocked SDK tests exercise actual serialized transcription and speech requests,
safe rejection, zero retries, content validation, quotas, owner isolation,
duplicate/concurrent claims, deletion during a call, transcript expiry/export and
strict text evidence regressions. The guarded Chromium scenario uses a synthetic
microphone and deterministic server provider: record → stop → consent → transcribe
→ edit/review → answer draft → save → reload → finish. It also generates synthetic
question audio and checks stop/mute controls. This is **not live recognition or
speech-quality verification**.

The test provider requires `JOBPILOT_VOICE_TEST_PROVIDER=true`, E2E mode and the
dedicated test database; production rejects test providers. Do not enable it in
normal operation. Apply additive migration `d1e2f3a4b5c6` once in deployment's
migration step. No existing records or document bytes need migration.

Offline plan, from `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.evaluation.voice_plan
```

It cannot execute live calls. Proposed separately authorized smoke: exactly two
requests, one 10-second synthetic WAV transcription and one 69-character question
speech request. Estimated USD 0.001000 + 0.001035 = **0.002035**, no retry/fallback.
Use the actual adapters; retain only safe status, transcript accuracy assessment,
duration/character estimates and available usage, not raw personal audio. Confirm
no interview advancement until review, audible question fidelity and cleanup.
Check the printed plan for the exact current text length/estimate before approving;
actual billing remains unknown. No live requests were made for this milestone.

### Completed offline checks

103 affected backend tests passed (voice, text interviews, account data,
configuration and deployment safeguards), plus 14 focused frontend tests and
two guarded connected browser scenarios. TypeScript and targeted ESLint passed.
The production frontend build passed with temporary example HTTPS backend and
same-origin API settings; local production-build configuration correctly failed
closed first. No secrets or persistent environment settings were changed.
No downgrade/reset tests were executed. These checks establish mocked behavior,
not live transcription accuracy, speech intelligibility or mobile compatibility.

Before/after read-only row counts and full-row fingerprints were compared for
all 27 pre-existing tables in both local development and persistent test databases.
Only `alembic_version` changed. The new voice table was empty after synthetic
test cleanup in both databases. No existing accounts, records or private files
were selected for deletion; fixture cleanup used its own generated identities.
The untracked preservation reports contain counts/hashes only, not row content.

Remaining setup: configure a backend speech key and project spending limits,
enable voice deliberately, configure HTTPS and proxy body/logging limits, apply
the additive migration once, and schedule retention cleanup. Live speech testing
requires separate authorization. Existing Google/Gmail setup blockers are
unchanged and are not dependencies of voice practice.
