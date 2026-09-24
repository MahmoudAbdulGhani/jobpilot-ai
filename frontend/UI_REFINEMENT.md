# JobPilot AI — refinement implementation and verification

This document supersedes the older redesign audit as the current implementation record. The original audit remains useful historical context, not a list of verified current defects.

## Design specification

Newsreader remains the display face, DM Sans the interface face, and Phosphor the icon library. Shared colors are defined once in `app/globals.css`: ivory paper, warm-white surfaces, dark ink, forest actions, and explicit semantic feedback colors. Workspace CSS no longer overrides the root palette.

The desktop sidebar is 240px; navigation becomes a focus-managed drawer below 1024px. Main gutters reduce to 16px on narrow screens. Body text is 16px, routine controls/supporting text 14px, and short badges/eyebrows 12px. Page headings reduce to 32px on mobile. Controls use 6px radii, panels 8px, and editor overlays 12px. Repeated card shadows are removed. Descriptive search limitations remain available in a disclosure.

## Route inventory and changes

| Route | Purpose and refinement | State / responsive coverage |
|---|---|---|
| `/` | Redirect to the new Overview | Auth and onboarding rules retained |
| `/overview` | Attention, recent saved jobs, application counts, latest advisory ranking, and toolkit links | Independent loading/error/retry per resource; real empty states; one-column mobile layout |
| `/jobs` | Search and manage saved opportunities | Promotional banner removed; readable rows; compact ranking empty state; mobile pagination |
| `/archive` | Retrieve archived opportunities | Shared collection/search/pagination states |
| `/jobs/[id]` | Read the posting, edit notes, prepare materials, apply, and track | Existing mounted tabs retained; readable text; missing-job versus network-error states; retry |
| `/jobs/[id]/interviews` | Review sources and start optional practice | Connected previously unused workflow styles to shared headers, grouped settings, and source preview; consent/history retained |
| `/interviews/[id]` | Answer, save, resume, and review practice | Shared header, question and feedback sections; corrected navigation label; text and voice workflows retained |
| `/discover` | Search sources, preview, explicitly import | Source caveats preserved; lengthy search limitations moved to a disclosure |
| `/applications` | Follow application status and history | Existing list and pagination retained; consistent type/surfaces |
| `/reminders` | Review and act on due/upcoming reminders | Accessible topbar link at mobile widths; existing confirm actions retained |
| `/insights` | Detailed private reporting and Q&A | Fixed Retry so it actually fetches again; existing evidence links retained |
| `/profile` | Maintain career facts | Consistent typography; explicit discard confirmation on Cancel; reload/close warning for unsaved edits |
| `/resumes` | Upload, review extraction, and optionally request profile suggestions | Reads persisted reviews; correct extraction endpoint; real server timestamps; accessible modal-to-suggestions flow |
| `/settings` | Connections, consent, account data | Structured permission choices and privacy rows; definition-list layout stacks on mobile |
| `/settings/usage` | Explain available usage and quotas | Existing limits and metering retained; consistent typography |
| `/login` | Sign in | Removed promotional sidebar; centered readable private-workspace form |
| `/register` | Invitation/registration | Shared restrained auth layout; existing validation retained |
| `/verify-email` | Verify ownership | Shared auth layout; existing success/error behavior retained |
| `/forgot-password` | Request account recovery | Shared auth layout; enumeration-safe responses retained |
| `/reset-password` | Set replacement credentials | Shared auth layout; existing token and confirmation behavior retained |
| `/onboarding` | Resume initial setup | Existing step rules retained; completion link goes to Overview |

## Functional and accessibility corrections

- Overview uses GET requests only. A ranking failure does not hide reminders, applications, or saved jobs. No synthetic KPIs, trends, model results, or activity timestamps are created.
- Completed-user login now opens Overview; incomplete onboarding still takes precedence.
- Legacy editor callers use the shared Radix dialog. This provides consistent focus containment, Escape handling, background inertness, and explicit focus restoration. Job/notes editors and extraction review warn before discarding edits.
- The resume metadata API does **not** contain extraction state. The library now reads the existing extraction endpoint separately. Reviewing first reads the saved extraction, then uses `POST /extract` only when no extraction exists or the user explicitly retries. Saving a changed draft invalidates review state from the server response.
- Removed client-generated review timestamps and kept the frontend wire type faithful to the backend schema. AI proposals remain separate, editable, explicitly generated, and explicitly applied.
- Mobile reminder navigation keeps an accessible name when its visible text is hidden.
- Mobile drawer Escape now restores focus to its opener. The previous controlled sheet had no registered trigger and lost that focus.
- Fit-analysis deletion uses the shared confirmation dialog and reports failed deletion while retaining the saved result.
- Settings action labels wrap at 320px rather than forcing the page wider. Resume toolbar touch targets are at least 44px on mobile.
- Interview pages now load their own workflow stylesheet and use its actual class names. Removed the synthetic-ID route prefetch and manual history mutation previously used to mask a development-server timing issue.
- Existing server contracts, authentication/security guards, consent semantics, database schemas, and production configuration validation remain unchanged.

## Audit reconciliation

| Finding | Final classification | Evidence |
|---|---|---|
| No home overview; completed login opens Jobs | Resolved | New route, redirect changes, connected login assertions |
| Competing root color palettes | Resolved | Palette owned by `globals.css`; page aliases reference it |
| Native and Radix editor dialogs coexist | Resolved | Legacy editor adapter now uses Radix; fit deletion migrated |
| Insights Retry only clears its error | Resolved | Retry refetches; regression test verifies recovery |
| Extraction uses a nonexistent POST endpoint | Resolved | Read existing extraction, explicitly POST `/extract` on first review/retry |
| Resume review state fabricated in the browser | Resolved | Complete server responses and timestamps retained; persisted review tested after reload |
| Settings overflows at 320px | Resolved | Wrapping action labels and shrinkable grid/fieldset children |
| Mobile drawer does not restore opener focus | Resolved | Explicit trigger ref and browser focus assertion |
| Interview styling exists but is not connected to its markup | Resolved | Imported styles, page headers, settings/question/feedback classes |
| Authenticated audit could not run without a local backend | Resolved | Isolated Docker test database and deterministic test providers |
| Every legacy page rule migrated to a primitive | Partial | Existing adapters and some scoped legacy CSS remain; no wholesale rewrite |
| Full assistive-technology/WCAG certification | Unverified | Keyboard/reflow/contrast checks are narrower than a complete accessibility audit |

### Contrast and interaction specification

The shared palette has approximately 14.98:1 ink/paper contrast, 5.64:1 muted/paper, 7.73:1 white/forest, 5.8:1 warning text/surface, and 3.44:1 input boundary/card. Midtone supporting text in the workspace, account, candidate-asset, and workflow styles was consolidated into darker semantic tokens. Low-contrast decorative separators remain deliberately separate from actionable input boundaries. Disabled controls retain their distinct treatment.

Focus indicators use forest outlines/rings. Primary buttons and mobile resume actions have 44px minimum targets; compact nonprimary controls and inline links are not all 44px squares. Reduced-motion rules remain enabled. The visual audit checks focus containment, Escape, discard/keep-editing, opener restoration, and mobile navigation.

## Test environment and evidence

`scripts/local-ui-checks.py` uses the existing loopback-only `jobpilot-db` Docker container and the dedicated `jobpilot_test` database. It obtains local container credentials without logging them, migrates only that test database, and passes process-local settings to Playwright. It does not edit `.env` or target the deployment database.

Run from the repository root:

```powershell
rtk proxy backend/.venv/Scripts/python.exe frontend/scripts/local-ui-checks.py
```

The initial authenticated sweep captured 28 images in `../evidence/refinement-initial/`. Those captures happened during the refinement and are an intermediate baseline, not screenshots of the original pre-redesign application. Original evidence files are kept separate. Playwright now writes screenshots to per-test output folders instead of overwriting them.

The repeatable visual audit covers desktop/mobile screenshots, all requested reflow widths, authenticated route navigation, the mobile navigation drawer, and editor discard/focus behavior. Functional suites cover populated workflows beyond the audit fixtures.

[Final screenshot index](../evidence/refinement-final/README.md): 40 page screenshots across 20 rendered routes, one mobile editor capture, and one 200% equivalent job-detail capture. The two earlier login captures are included separately for comparison.

Connected-test updates retain persistence, ownership isolation, source attribution, duplicate handling, PDF/DOCX export content, consent gates, application history, and deletion assertions. Fixtures opt into only the AI features their scenario requires. The resume suggestion test now explicitly verifies that an unsupported edited claim is rejected before applying a supported value.

### Scope and remaining limits

- Browser checks use Chromium and deterministic local providers. Real Gmail/OAuth, live discovery availability, paid AI models, and real microphone/speech services were not exercised; their existing contracts and consent rules are retained.
- The 200% equivalent reflow check uses a 744px CSS viewport at 2× pixel density for a 1488px desktop. Manual browser zoom, screen-reader testing, and a complete WCAG audit remain separate checks.
- Profile edits warn on Cancel and browser reload/close. A general guard against every internal SPA navigation is not implemented.
- Shared foundations are consolidated, but some scoped legacy rules and workflow-specific field editors remain. This pass does not claim a complete component-architecture rewrite.
- The original authenticated pre-redesign state was not captured. Intermediate snapshots are labeled accordingly, rather than presented as a true before/after comparison.
- Verification applies to the local working tree. Existing unrelated screenshots, backups, temporary run logs, historical audit documents, and backend helper scripts remain outside the proposed implementation changes.

### Coherent commit groups

1. **Overview and workspace foundations:** route/default destinations, read-only resource loading, Overview tests, shell navigation, shared palette, layout and typography.
2. **Workflow refinement and recovery:** dialogs/focus/discard behavior, job and Insights retry, resume extraction/provenance, profile editing, interview layout, related unit and connected regression updates. Include the test selectors and explicit fixture consents with the UI changes they exercise.
3. **Verification and handoff:** isolated local runner, Playwright configuration, responsive audit, this document, and the screenshot index. Review screenshot artifacts individually; do not bulk-stage the evidence directory or temporary files.

The existing dirty evidence files and unrelated untracked files should not be swept into these commits with `git add .`.

### Verification status

Results below refer to the **uncommitted working tree on 2026-09-24**, not the previous redesign commits. Screenshot inspection alone is not a claim of full WCAG conformance.

| Check | Exact result |
|---|---|
| `rtk npm run lint` (frontend) | Passed, exit 0 |
| `rtk npm run typecheck` (frontend) | Passed, exit 0 |
| `rtk proxy git -c core.safecrlf=false diff --check` | Passed, exit 0 |
| `rtk proxy npx.cmd vitest run --maxWorkers=1 --minWorkers=1 --reporter=json --outputFile=test-results/refinement-unit-final.json` (frontend) | **124 passed, 0 failed across 25 files**, exit 0. Final complete rerun after correcting the fit-analysis test cleanup hook. |
| Optimized `npm run build` | Passed, exit 0. Compilation, lint/type validation, static page generation, and build tracing completed. Used process-local `JOBPILOT_DEPLOYMENT=test`, `NEXT_PUBLIC_API_URL=/api`, and `JOBPILOT_BACKEND_ORIGIN=http://127.0.0.1:8010`. |
| Full connected suite: `rtk proxy backend/.venv/Scripts/python.exe frontend/scripts/local-ui-checks.py` | 23 passed, 1 failed in 6.9m. The failing interview deletion returned HTTP 204; its subsequent development-server route request exceeded the test's five-second wait. |
| Final targeted rerun: same runner with `tests/e2e/ui-audit.spec.ts tests/e2e/interviews.spec.ts` | **4 passed in 2.6m**, exit 0. The deletion test now asserts HTTP 204 and explicitly waits up to 15 seconds for the return route before asserting the empty history. Both text/voice workflows and both visual audits passed. |

All 24 distinct connected scenarios have passing results across the broad run and the final targeted rerun; a second full 24-test run was not performed. The final audit includes the last mobile alignment adjustments and refreshes the screenshot set.

The optimized build used the application's supported test deployment configuration. It does not validate a production backend origin or deployment. The HTTPS/same-origin production guards remain intact.

The final unit report is available locally in `test-results/refinement-unit-final.json` (generated, not part of the proposed source commits). No test failures remain unresolved.
