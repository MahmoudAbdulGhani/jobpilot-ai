# Career Journal design QA

- Source visual truth: `C:\Users\Admin\Downloads\JobPilot_Option_2\jobpilot-option-2\design\selected-option-2.png`
- Reference pixels: 1488 × 1058; desktop detail state.
- Implementation: `frontend/app/jobs/[id]/page.tsx` with `frontend/app/globals.css`.
- Intended comparison viewport: 1488 × 1058 CSS pixels at device scale factor 1.
- Browser-rendered implementation screenshot: unavailable.
- Full-view comparison evidence: source image was opened at original resolution; no browser-rendered implementation capture was available.
- Focused-region evidence: not performed because the implementation could not be rendered against a running backend session.

## Findings

- [P0] Connected visual and interaction QA is blocked. Docker Desktop is not running, so PostgreSQL and the authenticated backend cannot start. This environment also exposes no approved in-app browser tool. Login, persisted CRUD, two-user isolation, console inspection, keyboard/dialog checks, mobile capture, and side-by-side image comparison could not be exercised.
- Static implementation follows the approved Newsreader/DM Sans typography, ivory/forest tokens, horizontal navigation, detail hierarchy, right notes rail, responsive stacking, and Phosphor icon direction. These observations come from code inspection and are not a substitute for rendered evidence.

## Comparison history

- Initial pass: blocked before browser capture; no visual fix loop was possible.

## Implementation checklist

- Start Docker Desktop and the guarded PostgreSQL service.
- Run the backend and frontend with the README commands.
- Log in using a disposable guarded test account, create the selected reference job state, and capture desktop and mobile views.
- Compare the desktop capture side-by-side with the source and resolve all P0/P1/P2 differences.
- Exercise refresh, CSRF, CRUD, nullable clearing, pagination/search, logout state clearing, dialog focus, and ownership isolation.

final result: blocked
