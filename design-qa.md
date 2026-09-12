# Career Journal design QA

- Source visual truth: `C:\Users\Admin\Downloads\JobPilot_Option_2\jobpilot-option-2\design\selected-option-2.png`
- Browser implementation: `evidence/detail-desktop-initial.png`
- Side-by-side evidence: `evidence/comparison-desktop-final.png`
- Mobile evidence: `evidence/detail-mobile.png` and `evidence/dialog-mobile.png`
- Desktop: 1488 × 1058 CSS pixels at device scale factor 1; both compared images are 1488 × 1058 pixels.
- Mobile: 390 × 844 CSS pixels at device scale factor 1; full-page detail is 390 × 1785 pixels.
- State: authenticated disposable owner viewing a persisted active job with description, notes, location, and HTTP source URL.

## Full-view comparison

The normalized comparison places the approved source left and browser implementation right. Header height, content margins, reading/notes split, divider, headline hierarchy, note surface, borders, ivory background, forest actions, and density match. Real identity and the required deletion trash icon replace mock controls. The source-only “Example opportunity” label has no API field and is intentionally omitted.

## Focused checks

- Typography: Newsreader headings and DM Sans UI/body text render at intended weights, sizes, line heights, and wrapping.
- Layout: desktop proportions and rail alignment match; the layout stacks at 390 px without horizontal overflow.
- Tokens: paper `#faf8f4`, forest `#255c4d`, gray borders, and notes `#f3efe5` match the source.
- Assets: the source requires no raster imagery. Phosphor icons are used; no placeholder, emoji, CSS-drawn, or custom SVG assets appear.
- Copy: selected detail content matches; dates and identity use real test data rather than production seeds.
- Dialogs: opening focus, Escape close, focus restoration, internal scrolling, and mobile footer reachability were browser-tested.

## Interaction evidence

Chromium exercised login, refresh-cookie restoration after reload, persistence, editing, nullable location/source clearing, notes, server search, two-page pagination, archive, restore, deletion cancel/confirm, logout, missing/invalid IDs, and two-user isolation. Expected error responses produced no uncaught page errors. The backend used guarded `jobpilot_test`; development data was untouched.

## Comparison history

1. Initial comparison: P2 description hierarchy drift. Fixed with safe paragraph/heading/list parsing.
2. Initial dialog run: P1 focus absent after `showModal()`. Fixed by focusing the first field and restoring the opener.
3. Initial mobile dialog: P1 long form escaped its bounds. Fixed with dialog-owned scrolling and verified footer reachability.
4. Final comparison: no actionable P0/P1/P2 fidelity differences remain.

## Verification results

- Backend: 91 passed, 0 failed, 0 skipped; 24 warnings.
- Playwright Chromium: 2 passed, 0 failed, 0 skipped.
- Browser page errors: none.
- Frontend typecheck, lint, and production build: passed.

## Follow-up polish

- P3: saved-details dates use the browser locale’s numeric short form while the mock uses an abbreviated month.

final result: passed
