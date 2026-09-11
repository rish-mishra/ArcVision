# ArcVision — Final Visual Design Pass

Visual design only. No backend, CV, detector, tracker, outcome, mechanics,
coaching, verified-outcome, ground-truth, or demo-session change was made.
Every number, warning, badge, and disclosure behavior from the prior passes
is unchanged — only how it's drawn changed. **Nothing was published,
deployed, committed, or pushed.**

Revert path: `docs/screenshots/before/frontend_backup/` holds an exact copy
of the five frontend files as they stood before this pass, and
`docs/screenshots/before/BEFORE_FILE_HASHES.txt` records their SHA-256
hashes. To fully revert, copy those three files back over
`frontend/index.html`, `frontend/static/css/main.css`, and
`frontend/static/js/{app,charts,api}.js` and re-run
`scripts/export_demo.py`. (`index.html` and `api.js` were never touched
this pass — their hashes are identical before/after.)

## A. What looked vibe-coded before

Identified by actually inspecting the five BEFORE screenshots, not assumed:

1. **Hero background**: a decorative dual-color radial "glow blob"
   (`.hero::before`) sat behind the real basketball photo, adding nothing
   the photo itself didn't already provide — pure AI-startup-hero
   decoration.
2. **Hero photo itself was heavily washed out** — the overlay tint was
   strong enough that the actual court/hoop/houses read as barely-visible
   background noise rather than a real photo.
3. **"Try Interactive Demo" button** used an orange→teal linear gradient —
   a textbook generic-SaaS gradient CTA.
4. **Landing's three tip cards** put each icon inside a soft pastel-tinted
   rounded square — a very common "SaaS feature icon tile" pattern that
   added visual noise without adding information.
5. **Coach's "#1 Focus" card** had a decorative radial gradient wash
   (`.coach-focus::before`, an orange glow in the corner) behind otherwise
   plain content — decoration with no data behind it.
6. **Details/Mechanics tab was the worst offender**: five nearly-identical,
   very wide, heavily-padded white cards, each containing one narrow chart
   with a large dead-space gap to its right — a textbook "wall of
   identical rounded metric boxes." Traced to a real bug, not just a
   styling choice (section B item 6).
7. **Corner radii throughout were large** (`--radius-lg: 20px` on every
   major card/hero/panel) — softer and rounder than the rest of the app's
   fairly restrained, data-first tone suggested.
8. **Several tiny uppercase "eyebrow" labels** (YOUR #1 FOCUS, TRY THIS
   NEXT, KEEP THIS, MAKES VS. MISSES) at heavy 800-weight, wide
   letter-spacing — individually fine, collectively a bit "startup
   marketing" in tone.
9. **`.subtab-btn`** (Mechanics/Makes vs Misses/Consistency/Trends) used a
   full stadium-pill shape (`border-radius: 999px`) — "pill-shaped
   everything" for what's really a small segmented navigation control.

**What did NOT look vibe-coded and was left alone:** the primary Coach/
Shots/Replay/Details tab row (plain text + underline, no pills, already
restrained); the Shots-tab metric table (a real table, thin rules, no card
nesting); the small 8px outcome-color dots on shot chips (already minimal,
not "giant glowing badges"); the MADE/MISSED/VERIFIED/confidence-tier
badges (legitimate, sanctioned use of a badge for genuinely tiered
information); the overall typography scale and font choice; the
Consistency and Makes-vs-Misses sub-tabs (already appropriately
table/ranked-bar shaped, not narrow-chart-in-wide-card).

## B. Exact design changes

1. **`.hero::before` removed** — the decorative glow blob is gone; the real
   photo is now the hero's only visual interest.
2. **Hero photo overlay lightened** — the full-box linear-gradient tint
   (the layer explicitly *not* responsible for text contrast, per the
   original code's own comment) reduced and reshaped into three stops (8%
   top / 20% mid / 58% bottom) so the photo reads more clearly through the
   middle of the hero while staying strong enough at the very bottom for
   the CTA caption to stay legible (see the mid-pass fix below). The
   radial vignette that actually carries headline/lede text contrast was
   **not** touched.
3. **`.btn-demo` gradient removed** — now inherits `.btn`'s flat brand
   color and existing hover/active states, like every other button.
4. **`.tip-icon` boxes removed** — icons now render as plain colored
   pictograms (22px, no background tile), no change to the icons
   themselves.
5. **`.coach-focus::before` gradient wash removed**, replaced with a
   3px solid left border in the brand color — the same differentiation
   language already used elsewhere in Coach (`.coach-cue-primary`,
   `.coach-card-strength`). Also dropped the card's box-shadow (flat
   surface, consistent with its sibling cards) and tightened its padding
   slightly.
6. **Fixed a real layout-timing bug driving the Details "wall of empty
   cards" look**: `renderCoach()` builds *every* tab's content once,
   upfront, while only the Coach panel is visible — so when
   `Charts.perShotBarChart()` (and the three sibling chart functions)
   measured `container.clientWidth` to size the SVG, the Details tab was
   still `display:none` and reported `0`, silently falling back to a fixed
   640px design width regardless of how wide the actual card was. Fixed in
   `charts.js` by giving every chart SVG `style="width:100%;height:auto"`
   in addition to its `viewBox` — the internal geometry still degrades to
   the same 640px-design fallback when hidden, but the rendered box now
   scales uniformly (no distortion) to whatever the container turns out to
   be once visible. For an already-visible chart this is a no-op (real
   width already matched design width).
7. **Added `.metric-chart-grid`** (a responsive `auto-fit` 2-up grid,
   `minmax(min(420px, 100%), 1fr)`) and wrapped the Mechanics sub-tab's
   five chart cards and the Trends sub-tab's early/late chart cards in it
   — each card now sits close to its chart's natural size instead of
   stretching across the full page width. The `min(420px, 100%)` form was
   required, not optional: a plain `minmax(420px, 1fr)` overflowed
   horizontally on mobile (caught and fixed during this pass's own mobile
   check — see section K).
8. **`--radius-sm/md/lg` reduced** from 8/12/20px to 6/9/12px — a single
   token change that tightened every card, panel, chip, hero, and video
   frame corner consistently, without touching individual selectors.
9. **`.subtab-btn` radius** changed from a full pill (999px) to
   `var(--radius-sm)` — a rounded rectangle instead of a stadium shape.
10. **Eyebrow-label weight/spacing softened**: `.demo-banner-eyebrow`,
    `.coach-focus-eyebrow`, `.coach-cues-label`, `.coach-card-eyebrow` all
    went from `font-weight: 800` / ~.07em letter-spacing to `700` /
    ~.04-.05em — same uppercase labeling function, quieter execution.

## C. Elements intentionally preserved

- ArcVision name, logo mark, tagline ("See what your shot is really
  doing."), orange/teal brand pair, dark/light mode infrastructure — all
  untouched.
- The real basketball hero photo itself (not replaced, not re-cropped,
  only its overlay tint adjusted).
- Primary tab navigation (Coach/Shots/Replay/Details) — already
  restrained, not modified.
- The entire verified-outcome/measurement-notes/automatic-analysis-details
  information hierarchy from the prior two passes — byte-for-byte the same
  template structure, only CSS around it changed.
- Shots-tab metric table, Consistency/Makes-vs-Misses sub-tab layouts,
  outcome-color dots, badge system (MADE/MISSED/VERIFIED/confidence
  tiers).
- Jump-to-Shot behavior, all warning/quality-note data and wording.

## D. Landing assessment

Now reads as a real, calmer photo-led hero: the actual court/hoop/pose-trail
overlay is visible instead of washed to near-white, the CTA is a flat brand
button instead of a gradient pill, and the three tip cards use plain
colored icons instead of pastel tiles. No fake testimonials, no "AI-powered"
badges, no stat-padding — none were present before either, and none were
added. A reviewer still reaches "this is a basketball computer-vision
project" within seconds, now with a photo that actually looks like one.

## E. Coach assessment

The "#1 Focus" card lost its decorative gradient wash and now differentiates
itself the same way every other emphasized element in Coach already does — a
solid colored left border. The page reads more like a written analysis
(headline stats → one-line summary → focus → supporting evidence) and less
like a stack of interchangeable highlight cards. The two-column strength/
makes-vs-misses row is unchanged structurally (it already had asymmetric
left-border treatment for one of the two cards).

## F. Shots assessment

Essentially already correct before this pass (see section A) — chips and
the metric table got the same global corner/radius tightening as everything
else, nothing else changed. The verified-outcome hierarchy (Outcome →
mechanics → collapsed Measurement notes → collapsed Automatic analysis
details) is pixel-for-pixel the same template as before, just less rounded.

## G. Replay assessment

Video remains the clear centerpiece at its original size; the "Jump to
shot" panel and video frame both picked up the smaller corner radius. No
structural change — the empty space below the panel on a short session is
ordinary page-end whitespace, not a container being stretched to a fake
minimum height, so it was left alone rather than restructured for its own
sake.

## H. Details assessment

The biggest single change in this pass. Mechanics' five charts (and
Trends' early/late charts) now sit in a responsive two-column grid instead
of one chart per full-width card, and the charts themselves now reliably
fill their card (root-caused to a real render-timing bug, not styled
around). This page went from the clearest "wall of rounded boxes" complaint
to the page that most looks like a deliberate data/engineering tool.
Consistency and Makes-vs-Misses were already table/ranked-bar shaped and
untouched.

## I. Dark mode assessment

Checked directly (`docs/screenshots/after/dark_*.png`), not assumed from
the light-mode changes. Background stays a deep neutral, text contrast is
clean, the focus card's left-border accent reads clearly, MADE/MISSED bar
colors and the VERIFIED badge remain legible, the Details 2-column chart
grid works identically to light mode, and Shot 9's collapsed disclosures
render correctly. No stereotypical navy+glowing-cyan-border look — there
was no glow effect to begin with (verified by grep; the only two things
resembling "glow" in the whole codebase were the two gradients removed in
this pass), so nothing needed to be added or suppressed for dark mode
specifically.

## J. Light mode assessment

Checked directly, not inverted-and-assumed. Borders, muted text, and
card/surface distinction all still read correctly with the reduced radius
tokens; orange/teal contrast unchanged (no color values were touched, only
shapes); outcome labels and charts unaffected in hue, only in container
shape.

## K. Mobile assessment

Checked at 390px width across landing, Coach, Details, and Shot 9. One real
regression was caught and fixed during this pass: the new
`.metric-chart-grid`'s `minmax(420px, 1fr)` doesn't shrink below 420px by
itself, which overflowed the 390px viewport horizontally on the Details
tab. Fixed with `minmax(min(420px, 100%), 1fr)`, re-verified at 0px
overflow (`scrollWidth === innerWidth === 390` exactly). Landing, Coach,
and Shot 9 all reported zero overflow both before and after that fix.
Buttons, disclosures, and navigation remain usable at this width (the
Details sub-tab pill row scrolls horizontally within its own row via its
existing `overflow-x: auto`, not a new behavior).

## L. Before screenshot paths

- `docs/screenshots/before/01_landing.png`
- `docs/screenshots/before/02_coach.png`
- `docs/screenshots/before/03_shots.png`
- `docs/screenshots/before/04_replay.png`
- `docs/screenshots/before/05_details.png`
- `docs/screenshots/before/BEFORE_FILE_HASHES.txt` (SHA-256 of the five
  frontend files pre-pass)
- `docs/screenshots/before/frontend_backup/` (exact file copies for a
  clean revert)

All captured at 1440×900, light mode, from the real live demo before any
CSS/JS/HTML edit in this pass.

## M. After screenshot paths

Same five, same viewport, same demo, post-pass:

- `docs/screenshots/after/01_landing.png`
- `docs/screenshots/after/02_coach.png`
- `docs/screenshots/after/03_shots.png`
- `docs/screenshots/after/04_replay.png`
- `docs/screenshots/after/05_details.png`

Plus supplementary dark-mode and mobile captures taken for this pass's own
regression checking (sections I/K):
`docs/screenshots/after/dark_01_landing.png`,
`dark_02_coach.png`, `dark_03_details.png`, `dark_04_shot9.png`,
`mobile_01_landing.png`, `mobile_02_coach.png`, `mobile_03_details.png`,
`mobile_04_shot9.png`.

## N. Files changed

| File | Changed? |
|---|---|
| `frontend/index.html` | No (hash identical before/after) |
| `frontend/static/css/main.css` | Yes — see section B |
| `frontend/static/js/app.js` | Yes — `.metric-chart-grid` wrapper added around Mechanics and Trends chart cards only |
| `frontend/static/js/charts.js` | Yes — responsive `style` attribute added to all 4 chart-drawing functions' `<svg>` elements |
| `frontend/static/js/api.js` | No (hash identical before/after) |
| `docs/FINAL_VISUAL_DESIGN_PASS.md` | New — this report |
| `docs/screenshots/before/*`, `docs/screenshots/after/*` | New — before/after evidence |

## O. Tests before/after

**253 before, 253 after — unchanged.** This pass added no new testable
behavior beyond what the existing suite already covers (the chart-grid
wrapper and responsive-SVG change are pure presentation with no new
data/logic branch; the existing `test_frontend_regressions.py` and
`test_export_demo.py` source-pattern tests were re-run and still hold since
none of the strings/functions they check were touched). Full suite
re-run clean at the end of this pass: `253 passed`.

## P. Dist regenerated

**YES** — three times during this pass (once after the main design pass,
once after the hero-caption-legibility fix, once after the mobile grid
overflow fix), each followed by a fresh `scripts/export_demo.py` run and a
`253 passed` test confirmation before regenerating.

## Q. Console/network result

Full `scripts/browser_qa.py` sweep (landing → Coach → Shots → shot detail →
Replay → full 19-attempt Jump-to-Shot sweep → Details → Methodology → dark
mode → tablet → mobile) re-run against the final `dist/`: **zero console
errors, zero page errors.** `network_failures` contains only the same
benign, expected `net::ERR_ABORTED` entries on `annotated.mp4` from seek
cancellation already explained in the prior passes' reports (no `4xx`/`5xx`
ever logged, every seek still succeeds).

## R. Functionality regression result

All explicitly requested checks, actually re-verified this pass (not
assumed from the visual changes being "just CSS"):

- Landing, Coach, Shots, Replay, Details: all render correctly (section
  D-H, screenshots).
- Methodology: still renders (`methodology_mentions_verified: true`,
  `methodology_render_error: null` in the browser_qa run).
- Measurement notes: still collapse by default, verified visually on Shot
  9 (dark and light).
- Automatic analysis details: still collapse by default, same shot.
- Verified outcomes remain primary: Shot 9 still shows "MISSED VERIFIED" as
  the headline Outcome row in both themes.
- All 11 shots present: `shot_chip_count: 11`, `replay_chip_count: 11`.
- 8 MADE / 3 MISSED / 72.7%: unchanged in `dist/demo/session.json`
  (untouched by this pass — no export-time logic was modified, only
  frontend presentation).
- Jump to Shot: **19/19** successful seeks (the full torture pattern +
  1→11 sweep), re-run against this pass's final `dist/`.
- Dark mode: works (section I).
- Light mode: works (section J).
- Mobile: works, one real overflow regression caught and fixed during this
  same pass (section K).
- Console/network clean (section Q).
- Full test suite: 253/253 (section O).

## S. Anything uncertain

- The Replay page's empty space below the video/jump-panel row was
  reviewed but deliberately left alone — restructuring it felt like
  redesign-for-its-own-sake rather than fixing a real problem, per the
  brief's own restraint instruction. Flagging it here in case the user
  disagrees and wants it tightened.
- The `.coach-secondary-grid` ("Keep this" / "Makes vs. misses") pair still
  uses the base `.card` shadow+radius rather than a fully bespoke
  treatment per data type (section 12's spirit) — left as-is since they're
  both short text blurbs, not data visualizations, and already
  differentiate via one having a colored left border; a bigger redesign
  there felt unnecessary for what they are.
- Eyebrow-label softening (item 10 in section B) is a light touch by
  design; if the user wants them toned down further (or removed as a
  label style entirely in favor of something else), that's a quick
  follow-up rather than a re-do.

## T. READY FOR MY VISUAL APPROVAL

**YES.** All requested BEFORE/AFTER evidence is captured at matching
viewports, the two regressions this pass's own changes introduced (hero
caption legibility, mobile Details overflow) were both caught by this
pass's own review process and fixed before finalizing — not left for the
user to find — full regression checklist re-verified against the actual
final `dist/`, and a clean, file-level revert path is recorded if the
direction isn't wanted.
