# Single synthetic production-profile diagnostic

UTC request timestamp: 2026-09-17T07:30:08Z. Exactly one HTTP request; no retry, fallback or rerun. Groq Responses endpoint, openai/gpt-oss-20b, low reasoning, completion cap 2,250; actual profile adapter and strict validation.

Dry-run reservation: 5,743 input + 2,250 output = 7,993 tokens. Calculated ceiling $0.001105725; rounded upward $0.001106. Matching final serialized request was verified before transport.

HTTP 200; provider completed; contract_pass. All required top-level and nested wire fields were present. Five suggestions passed unchanged local evidence validation: headline Backend engineer; location Beirut; skills Python, PostgreSQL (one combined entry); experience Engineer at Cedar Demo, 2021-2024, with booking API project note; education BSc Computer Science, Example University, 2020. No provider error explanation or failed generation was supplied.

Every non-null value and every evidence quote occurs verbatim in the synthetic source. However, the experience quote covers role/employer/dates only, not the project note. The project appears separately in the source, and its attribution to the employer is not explicit. This is a semantic review limitation despite the local contract pass. Skills are not separated into individual entries. Education field is null, with Computer Science retained in the degree string.

No target source fact was omitted. There was no source language fact, and none was invented. Name/email are outside this extraction contract. Accepted means accepted by validation, not applied or approved by a user. This single synthetic pass does not establish general integration correctness.

Available usage: 1,072 input tokens, 232 output tokens, 1,304 total; reported reasoning tokens 14 (part of output). Usage-based cost estimate at configured rates: $0.000150. Actual billed cost remains unknown; account billing is unverified.

The live-gate environment variable was restored to its previous presence/value in finally. Bounded redacted response diagnostics are in the companion JSON. No credentials, headers, unrestricted response/error bodies or reasoning text were recorded. No further request or settings change was made.
