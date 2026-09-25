# JobPilot AI landing page

## Design and motion specification

- Preserve the existing Newsreader / DM Sans identity and tokens: paper `#faf8f4`, ink `#20231f`, forest `#255c4d`, line `#dfddd5`. Add a deep forest stage `#173f35`, soft sage, fine grids, restrained document shadows, and generous editorial spacing. No raster assets or remote fonts are needed.
- Structure: sticky navigation; outcome-led hero and layered document scene; five-chapter workflow; asymmetric feature composition; interactive sample workspace; explicit review demonstration; FAQ; final sign-in CTA and existing navigation.
- Hero storyboard: masked heading, arriving CV, evidence highlighting, extracted facts, job card, then review receipt. One finite GSAP sequence. Fine-pointer depth is restrained and stops when offscreen. All content is initially rendered and readable without JavaScript.
- Workflow storyboard: a single reversible ScrollTrigger timeline carries the same candidate through evidence, profile, opportunity, review, and tracking. SVG paths draw the connections; chapter indicators follow progress. Normal document scrolling drives a proportional pin duration.
- Dependencies: existing Next 15 / React 19 / Tailwind 4, npm lockfile, shadcn/Radix primitives and Phosphor icons. Add only GSAP, scoped to landing components. Use CSS for hover, press, dialog, filter, and accordion transitions.
- Mobile: vertical chapters instead of pinning, readable full-width cards, stacked hero, accessible sheet navigation. Reduced motion: all chapters visible; no pinning, parallax, or elaborate transitions. Match-media cleanup handles preference and breakpoint changes.
- Routing: `/` currently redirects to `/overview`. Make it public while keeping signed-in visitors directed to `/overview` and all existing protected routes unchanged. CTA goes to `/login`; invited users retain the existing invitation flow. No signup promises.
- Claims: sample scenes explicitly say “Illustrative product preview.” No fabricated success claims. Mail delivery and Google integration are not advertised as operational. AI/provider features remain conditional on configuration and consent.

## Workspace

Implementation is isolated on `feat/editorial-landing-page` in `C:/Users/Admin/Desktop/jobpilot-ai-landing`. Existing changes in the original worktree are untouched. UI/UX Pro Max was not found in installed skill locations; existing project design guidance was used. No environment files, backend, deployment settings, or migrations are changed.

## Motion references

Implementation follows the official [GSAP matchMedia lifecycle](https://gsap.com/docs/v3/GSAP/gsap.matchMedia()/) and [ScrollTrigger documentation](https://gsap.com/docs/v3/Plugins/ScrollTrigger/).

## Implemented behavior

The hero uses a finite GSAP sequence: masked type, CV arrival, highlighted evidence, extracted facts, job preview, and review receipt. Fine-pointer depth is limited to three degrees and pauses offscreen. The primary CTA remains outside the animated elements. Mobile uses full-width document cards rather than a scaled desktop composition.

The workflow has one reversible timeline and five chapters. SVG connections draw as evidence moves through the story. Its active state follows actual scrubbed timeline time; inactive preview scenes are inert, while the complete chapter narrative remains accessible to assistive technology. GSAP matchMedia contexts revert styles, pins, timelines, and event handlers on resize, motion-preference changes, and unmount. Font readiness triggers a refresh. At mobile/tablet widths and with reduced motion, all five chapters are ordinary document content.

The local demo switches between three role preferences, opens a shadcn/Radix dialog, and supports keyboard navigation between CV, cover-letter, and email panels. Editing the sample headline or selecting the suggestion updates the review summary. Approval requires an explicit click, changes only local state, and moves focus to the confirmation. Cancel, edit again, and reset are supported. No fake loading states or provider requests occur.

Authentication logic only gains a public-root exception and the previous signed-in root destination. Login/onboarding behavior, session handling, API code, and protected routes retain their existing behavior.

## Verification

- `rtk npm run test`: **133 tests passed across 27 files**. The existing resume-download test prints a jsdom unsupported-navigation diagnostic while passing; the browser suite has no console errors.
- `rtk npm run lint`: passed without warnings after final code fixes.
- `rtk npm run typecheck`: passed.
- Production build: passed, all 21 static pages generated, using process-local `JOBPILOT_DEPLOYMENT=local` and `NEXT_PUBLIC_API_URL=/api`. The page is statically rendered. First-load JavaScript for `/` is 187 kB; animation imports are confined to landing components.
- `rtk npx playwright test --config playwright.landing.config.ts`: **18 tests passed** against the production server in Chromium. The suite fails on browser console errors or unhandled exceptions.
- Verified 360, 390, 768, 1024, and 1440 px layouts; no horizontal overflow; keyboard menu/FAQ/dialog/tabs; focus restoration; sample filters and review approval; no sample API calls; mobile dialog boundaries; all five reduced-motion chapters; JavaScript-disabled rendering; scroll beginning/middle/end; reverse scrolling; resize and live motion-preference changes; navigation cleanup; signed-in root and application route; logged-out protected-route redirects.
- The 1024×768 review chapter has explicit content-fit assertions inside the product stage.
- GSAP only is added to the existing npm lockfile. No unrelated dependency upgrades.

Run the local production preview from `frontend`:

```powershell
rtk proxy powershell -NoProfile -File scripts/landing-local.ps1 build
rtk proxy powershell -NoProfile -File scripts/landing-local.ps1 start
```

Open `http://localhost:3025`. The standalone browser config can also start its own development server when no preview server is running.

### Scope and remaining limits

Browser application/API responses were mocked; no live AI, email, database, OAuth, billing, or backend integration was exercised. Registration modes were established from existing source, with sign-in-only CTAs on this page. Gmail is explicitly described as optional and live integration as unverified. No public legal/contact route exists to link, so none is invented. Validation used Chromium; Safari/Firefox and manual screen-reader testing were not performed. UI/UX Pro Max is unavailable in the installed skill directories.

## Visual evidence

All screenshots were captured from the running production build using Playwright. Full-page captures use reduced motion to show every chapter. Desktop motion captures use actual scrolled animation states. The mobile product-only capture hides the sticky header during capture so it does not obscure the selected region.

- [Desktop hero](evidence/landing/desktop-hero.png)
- [Desktop complete page, reduced motion](evidence/landing/desktop-1440.png)
- [Mobile hero](evidence/landing/mobile-hero-390.png)
- [Mobile product scene](evidence/landing/mobile-product-scene.png)
- [Mobile complete page](evidence/landing/mobile-390.png)
- [Workflow beginning](evidence/landing/workflow-beginning.png)
- [Workflow middle](evidence/landing/workflow-middle.png)
- [Workflow end](evidence/landing/workflow-end.png)
- [Workflow review at 1024×768](evidence/landing/workflow-review-1024x768.png)
- [Application dialog](evidence/landing/application-preview.png)
- [Mobile application dialog](evidence/landing/application-preview-mobile.png)
- [Explicit demo approval](evidence/landing/review-approved.png)

## Exact changed files

Modified:

1. `frontend/app/page.tsx`
2. `frontend/lib/auth.tsx`
3. `frontend/package.json`
4. `frontend/package-lock.json`

Added:

1. `LANDING_PAGE.md`
2. `frontend/app/landing.css`
3. `frontend/components/landing/LandingHeader.tsx`
4. `frontend/components/landing/Hero.tsx`
5. `frontend/components/landing/WorkflowStory.tsx`
6. `frontend/components/landing/workflow.css`
7. `frontend/components/landing/ProductPreview.tsx`
8. `frontend/components/landing/ReviewControl.tsx`
9. `frontend/components/landing/preview.css`
10. `frontend/tests/landing-preview.test.tsx`
11. `frontend/tests/landing-e2e/landing.spec.ts`
12. `frontend/playwright.landing.config.ts`
13. `frontend/scripts/landing-local.ps1`
14. `evidence/landing/desktop-hero.png`
15. `evidence/landing/desktop-1440.png`
16. `evidence/landing/mobile-hero-390.png`
17. `evidence/landing/mobile-product-scene.png`
18. `evidence/landing/mobile-390.png`
19. `evidence/landing/workflow-beginning.png`
20. `evidence/landing/workflow-middle.png`
21. `evidence/landing/workflow-end.png`
22. `evidence/landing/workflow-review-1024x768.png`
23. `evidence/landing/application-preview.png`
24. `evidence/landing/application-preview-mobile.png`
25. `evidence/landing/review-approved.png`

All work is uncommitted and undeployed. The original worktree and its pre-existing modifications remain untouched.
