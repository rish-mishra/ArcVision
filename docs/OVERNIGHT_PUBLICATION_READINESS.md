# ArcVision — Overnight Publication Readiness Pass

Unattended finalization pass over the "FINAL DEMO MODE" work. Scope: verify the
precommitted verified-outcome demo actually works in a real browser, audit
production/research separation, security/privacy, git hygiene, licensing, and
GitHub Pages readiness, and report exact next steps. **Nothing was published,
deployed, committed, or pushed.** No CV/threshold/detector/tracker/outcome/
biomechanics/coaching code was touched, and no verified ground-truth labels
were changed.

Two genuine, previously-undetected bugs were found and fixed during this pass
(both frontend/export bugs, not outcome engineering — see sections C and K).
One suspected bug (Jump-to-Shot seeking) turned out to be a false alarm caused
by the ad hoc local QA server, not the app — see section H.

---

## A. Initial state (baseline)

- Branch: `master`. HEAD: `b08c2fe` ("Freeze final demo ground truth before
  inference"), previous `fa9ee0d` ("Freeze Video 4 ground truth before running
  inference").
- Full test suite at the start of this pass: **232 passed**, 0 failed.
- Production/research separation: confirmed clean by direct filesystem scan of
  every `.py` file under `app/` (excluding `app/research/` itself) for any
  reference to `app.research` — **zero matches**.
- Demo session shot count: the session pointed to by `export_demo.py`
  (`DEMO_SESSION_ID`) at the start of this pass was `ab556626332b440e`, with
  11 detected shots — matching the expected post-segmentation-fix state.
- Frozen ground truth (`docs/FINAL_DEMO_GROUND_TRUTH.md`): sequence confirmed
  MADE, MADE, MADE, MADE, MISSED, MADE, MADE, MISSED, MISSED, MADE, MADE (8
  made / 3 missed / 11 total) — matches the expected baseline exactly, no
  discrepancy.
- Verified-outcome mapping: 1:1 against all 11 `shot_index` values, enforced
  by `apply_verified_outcomes()`'s own hard check (raises `ExportError` on any
  mismatch) and by test `test_g_all_11_mappings_align_with_frozen_ground_truth_doc`.
- Automatic (`automatic_outcome`) values confirmed preserved separately from
  `verified_outcome` on every shot, both in code (`apply_verified_outcomes`
  never overwrites, only annotates) and by test
  `test_c_raw_automatic_outcome_is_preserved_not_overwritten`.

No baseline assumption was found to be false. Proceeded.

## B. Final tests (after all fixes in this pass)

**232 passed**, 0 failed — identical count to the baseline. All fixes made
during this pass (see section C) are export-tooling/frontend/doc fixes with
zero effect on existing test coverage; no new test failures were introduced
and no tests were weakened or deleted to make the count match.

(Test coverage itself was not expanded this pass beyond what "FINAL DEMO MODE"
already added — that work is described in this repo's prior session and is
out of scope for a from-scratch re-audit here.)

## C. Files changed overnight

Code/content changes:

| File | What changed | Why |
|---|---|---|
| `app/analytics/stats_utils.py` | `compare_groups()` now treats a NaN or Infinite `p_value` (which `scipy.stats.ttest_ind` can legitimately return for small/degenerate samples) the same as "unavailable," setting it to `None` instead of letting the NaN float through. | **Critical bug.** A NaN `p_value` was being serialized into the exported `session.json` as the literal token `NaN`, which is valid in Python's `json.dumps` but is **not valid JSON** per spec. The browser's `JSON.parse` correctly rejected the entire payload, so nothing past the landing page ever rendered (see section K). |
| `scripts/export_demo.py` | `session.json` is now written with `json.dumps(..., allow_nan=False)`, wrapped to raise a clear `ExportError` if it ever fails. Also updated `DEMO_SESSION_ID` to a freshly-generated session (see below). | Defense in depth: any future NaN/Infinity anywhere in a session payload now fails the export loudly instead of silently shipping a broken bundle. |
| `frontend/static/js/app.js` | `initTabs()` (the Coach/Shots/Replay/Details tab switcher) now only removes the `.active` class from the four panels it actually owns, instead of every element matching `.tab-panel` in the whole document. | **Critical bug.** The standalone Methodology page (`#tab-methodology-standalone`) also carries the `.tab-panel` class for its own show/hide styling but is a separate view, not one of the dashboard's four tabs. Its `active` class is only ever set once, in the static HTML — so the first click on *any* dashboard tab silently stripped it, and the Methodology page (which carries the required verified-outcome transparency note) rendered permanently blank for the rest of that session. |
| `docs/METHODOLOGY.md` | Title and two body references changed from "FormAI Basketball" / "FormAI" to "ArcVision" / "ArcVision". | Stale pre-rebrand product name in a current, user-facing document (this file is shipped verbatim into the public demo as `demo/methodology.md`). |
| `README.md` | "218 tests passing" → "232 tests passing". | Stale current-state test count; the actual, just-verified count is 232. (Historical research-report documents that cite older counts as of a past date were deliberately left untouched — see section O.) |
| `.gitignore` | Added `/ShuttleSight/`. | Safety net only — see section S. Does not move, delete, or otherwise touch the ShuttleSight directory. |
| `scripts/create_final_demo_session.py` *(pre-existing this session)* | Re-run once, producing a fresh session `fee1c3bcd7b84322` under the current code (including the `stats_utils.py` fix above), replacing `ab556626332b440e` (which was created before that fix and had a NaN baked into its stored `analysis_json`). | The stored `analysis_json` for a completed session is computed once at pipeline-run time and never recomputed at export time, so the NaN fix required a fresh pipeline run, not just a code change. |
| `scripts/export_demo.py` | `DEMO_SESSION_ID` updated to `fee1c3bcd7b84322`. | Points the export at the NaN-free session above. |
| `scripts/browser_qa.py` | New QA driver (Playwright), then iteratively hardened: demo-entry CTA selector prioritized to the real button text ("Try Interactive Demo"); shot-chip waits scoped to `#tab-shots`/`#tab-replay` specifically (a bare `.shot-chip` selector ambiguously matched both, and Playwright's "visible" wait doesn't resolve well against 22 matches); the Replay "Jump to shot" chips are matched by their `#N` text (they carry a `data-t` seek-time attribute, not `data-shot`, unlike the Shots-tab chips); Jump-to-Shot results now verify the actual seek landed near the target time rather than just "did a click happen." | Not shipped to users — a QA tool only. Written and fixed so it exercises the real DOM instead of silently reporting false negatives. |
| `scripts/range_http_server.py` | New file: a minimal static server that supports HTTP Range requests. | `python -m http.server` (the obvious "serve `dist/` locally" choice) **does not implement Range requests at all** (confirmed by direct `curl -H "Range: ..."` — it returns `200`/full body, not `206`/partial). Chromium reports a video served this way as having `seekable = [[0, 0]]`, so every Jump-to-Shot click silently failed to seek — this looked exactly like an app bug until traced to the test server. See section H. Not part of the shipped app or the exported `dist/` bundle. |
| `docs/OVERNIGHT_PUBLICATION_READINESS.md` | This report (new). | Deliverable for this pass. |

`dist/` was regenerated three times during this pass (after the `stats_utils.py`
fix + new session, after the `app.js` fix, and after the `docs/METHODOLOGY.md`
branding fix) and reflects all of the above as of the end of this pass.

Note: `docs/VIDEO4_EVALUATION_PROTOCOL.md` shows as modified in `git status`
from *before* this pass began (part of the prior session's work, not this
one) — left untouched here; flagged in section R for the user's own review
before staging.

## D. Browser desktop QA (1440×900)

Actually driven with a real headless Chromium (Playwright), not inferred from
source — screenshots saved under `data/diagnostics/browser_qa/`.

- **Landing** — real ArcVision branding, hero image, "Try Interactive Demo"
  CTA, "Analyze your own footage" card, three tip cards, footer. No FormAI
  branding, no placeholder/debug text.
- **Coach** — headline `11 Shots / 8 Made / 3 Missed / 72.7%` (from verified
  outcomes), a real coaching narrative ("Your knee angle at release was the
  most consistent part of your form...", "#1 Focus: Shot timing", "Keep this:
  Leg extension at release", "Makes vs. misses: no clear difference"),
  "Moderate evidence" badge.
- **Shots** — all 11 chips present, colored correctly (green/red matching the
  frozen ground truth exactly). Shot 1 detail view shows `Outcome: MADE`
  with an orange **"Verified outcome"** badge, and *separately*,
  `Automatic detection: UNKNOWN — 0.00 (LOW)` with its real reason ("rim
  interaction not sufficiently observed") — exactly the required
  never-conflated presentation. Full per-shot metric table (angles, release
  height, trajectory straightness/apex, outcome evidence internals) renders
  with real numbers.
- **Replay** — video loads and plays (frame shows real pose-skeleton + hoop
  overlay), "Jump to shot" panel with all 11 chips, correctly colored.
- **Details** — Mechanics/Makes vs Misses/Consistency/Trends sub-tabs present;
  charts render per-shot bars colored by **automatic** outcome (gray =
  automatic-unknown), which is correct and intentional — mechanics/coaching
  are explicitly required to stay automatic, only the primary Outcome field
  uses the verified label (see section M for whether this reads clearly to a
  viewer).
- **Methodology** (footer "How this works" link) — after the section-C fix,
  renders the full document, including the verified-outcomes transparency
  note (confirmed present via `methodology_mentions_verified: true`).

## E. Tablet QA (768×1024)

Landing page screenshot captured. `document.body.scrollWidth` vs
`window.innerWidth`: **768 vs 768 — no horizontal overflow.** No redesign
performed (none needed).

## F. Mobile QA (390×844)

Landing page screenshot captured and visually reviewed: hero, CTA, and all
three tip cards stack cleanly, no clipped text, no overflow.
`scrollWidth`/`innerWidth`: **390 vs 390 — no horizontal overflow.**

## G. Dark / light mode

Both captured at 1440×900. Light mode covered in section D. Dark mode
(landing page): correct dark surface colors, readable text contrast, brand
gradient CTA button unchanged, hero image and pose-trail overlay still
legible. No redesign performed.

## H. Jump to Shot — 11/11 (plus the specified navigation torture pattern)

**Real result: 19/19 successful seeks** — the specified torture pattern
(1→11→3→9→4→10→2→8) followed by a full 1→11 sweep, every one verified by
reading `video.currentTime` back after the click and confirming it landed
within 1 second of that shot's actual `start_time_sec`. All 19 attempts:
`ok: true`, `seek_close_enough: true`.

**This did not work on the first attempt**, and the first-attempt failure
looked exactly like a real product bug: every click left `video.currentTime`
stuck near 0.6s regardless of target. Traced (not assumed) to the QA
harness: `python -m http.server` — the obvious way to "serve `dist/` locally"
— does not support HTTP Range requests (confirmed with a direct
`curl -H "Range: bytes=..."`, which returned a full `200` body instead of
`206 Partial Content`), so Chromium reported the video's `seekable` range as
only `[0, 0]` no matter how much had downloaded. Re-served the identical,
unmodified `dist/` through a small Range-capable server
(`scripts/range_http_server.py`, QA-only, not shipped) and every seek worked
correctly. **This was not an ArcVision bug** — any real static host used for
actual publication (GitHub Pages, Netlify, S3, nginx, etc.) supports Range
requests natively.

## I. Demo totals

From the regenerated `dist/demo/session.json`, read back and verified
directly (not assumed from code):

- `session_summary`: `made=8, missed=3, unknown=0, shooting_percentage=72.7,
  total_shots_detected=11`.
- `automatic_made=2, automatic_missed=5, automatic_unknown=4,
  automatic_shooting_percentage=28.6` — preserved, never overwritten.
- `outcomes_verified: true`.

## J. Demo-data integrity

- 11 shots, indices `[1..11]`, unique, contiguous, sorted.
- Every shot's `start_time_sec < release_time_sec < end_time_sec` — checked
  programmatically for all 11, all true.
- All 11 `verified_outcome` values compared directly against
  `docs/FINAL_DEMO_GROUND_TRUTH.md`'s table (parsed independently, not
  hardcoded twice) — **zero mismatches**.
- `automatic_outcome` present and distinct from `verified_outcome` on every
  shot.
- Mechanics present on every shot (confirmed via the Details charts
  rendering real values for knee/elbow/torso/release-height/prep-duration
  across the shots that have each metric).
- No stale 13-shot data anywhere in the current export (the 13-shot,
  pre-segmentation-fix session `29c7e751775e4f20` is no longer referenced by
  `export_demo.py` and does not appear in `dist/`).
- No stale session-ID references found in `dist/` (checked directly — the
  only session ID appearing anywhere in the export is the current
  `fee1c3bcd7b84322`).
- The full exported `session.json` now parses successfully under Python's
  **strict** `json.loads` (i.e., genuinely valid JSON, not just "the specific
  fields I checked look right") — confirmed directly, not inferred.
- Coaching narrative text (Coach tab, section D) confirms it is still
  generated from real automatic analysis ("Your knee angle at release was
  the most consistent...", "Makes vs. misses: no clear difference") — it
  does not reference or depend on the verified labels.

## K. Media / audio status

- `demo/annotated.mp4`: 11,770,020 bytes (~11.2 MB), plays correctly in
  Chromium at all tested viewports, duration 98.5s matches
  `session_summary` metadata, shows real pose/ball/hoop overlays.
- Not muted this pass — no audio-stream change was needed or made; the
  original file was not touched, only copied by `export_demo.py` as before.
- The one network item worth noting: repeated
  `net::ERR_ABORTED GET .../demo/annotated.mp4` entries appeared during the
  Jump-to-Shot test. This is **expected, benign browser behavior** — setting
  `video.currentTime` to a new position cancels the previous in-flight
  range fetch for the old position and starts a new one; it is not a real
  network failure (no `4xx`/`5xx` response was ever logged, and every seek
  in section H succeeded).

## L. Console / network errors

Across every view (landing, dashboard, all four tabs, methodology, dark
mode, tablet, mobile) and the full Jump-to-Shot sweep: **zero
`console.error`/`console.warning` entries, zero uncaught page errors.** The
only `network_failures` entries are the benign seek-cancellation aborts
described in section K. No 404s, no missing assets, no stale references.

## M. Verified-outcome transparency wording

- The dashboard header banner reads: *"INTERACTIVE DEMO · REAL ARCVISION
  ANALYSIS — This session was processed by ArcVision's actual RF-DETR
  detection and pose/biomechanics pipeline. The public demo shows
  precomputed results so it can be hosted for free without requiring a
  GPU — nothing here is fabricated or simulated."* — accurate, calm, not
  alarming, and does not itself claim the *outcomes* are automatic (it
  correctly scopes the claim to detection/tracking/biomechanics).
- Per-shot: "MADE — Verified outcome" is shown as the primary result, with
  "Automatic detection: UNKNOWN — 0.00 (LOW)" and its real reason shown
  immediately below, never conflated (section D).
- The Methodology page (now rendering correctly — section D/C) carries the
  required transparency note appended by `_write_demo_methodology()`; the
  *source* `docs/METHODOLOGY.md` was confirmed untouched by that
  append-only step.
- One judgment call surfaced, not a defect: the Details-tab mechanics
  charts color bars by **automatic** outcome (so a verified-MADE shot with
  an automatic-unknown classification shows as gray, not green). This is
  correct per the explicit requirement that mechanics/coaching stay
  automatic — flagging it here only so it's a documented, deliberate
  choice rather than something noticed later and mistaken for
  inconsistency. No change made.
- Nothing in this pass weakened the transparency wording to make the demo
  look better, and nothing added a stronger claim than the underlying data
  supports.

## N. README readiness (three-persona read)

Read in full (377 lines) from an admissions-reviewer, cloning-developer, and
technical-mentor lens:

- Branding: consistently "ArcVision" throughout; no FormAI references found.
- Product explanation, feature list, and "What this is not" section are
  clear and appropriately scoped for a non-technical skim.
- Architecture section documents each pipeline stage with real file paths.
- RF-DETR explained with model/dataset/license link
  (roboflow/rf-detr, Apache-2.0; "Basketball Shooting Robot" dataset,
  Roboflow Universe, CC BY 4.0, 9,612 images / 17,258 boxes) and an honest
  account of the YOLO fallback stack's own license caveat (Ultralytics
  AGPL-3.0 note, explicit "would need re-licensing for commercial/hosted
  deployment").
- MediaPipe BlazePose explained with its Apache-2.0 license noted.
- Coaching and demo sections explained (see section M) without overstating
  what the demo represents.
- Windows install instructions present, PowerShell-specific, describe the
  checkpoint dependency and where to get it.
- Checkpoint fallback: explicitly documented as **not implemented** — the
  RF-DETR ball/rim detector raises a clear `FileNotFoundError` naming the
  expected path and explaining *why* there's no generic fallback (ball/rim
  aren't COCO classes), rather than silently degrading. Confirmed by
  reading `app/vision/detection/ball_rim_detector_rfdetr.py` directly.
- Evaluation & limitations sections are candid, including a **failed**
  blind test reported as such rather than omitted.
- Test count corrected to 232 (section C); no other unsupported accuracy
  claims found.
- README does not claim the verified demo outcomes are automatic
  predictions anywhere (confirmed — no "AI predicted" / "model confidence" /
  accuracy-percentage language tied to the demo).
- Screenshots: none currently embedded in the README (see section W for a
  recommended set/viewport list; none were fabricated this pass).
- No LICENSE section claims a license the repo doesn't actually have (see
  section U — this is the one real blocker).

## O. Documentation consistency scan

Searched all of `docs/*.md` and `README.md` for stale test counts (109, 195,
197, 218, 225), old shot-count claims, old branding, and old session IDs.

- `README.md`'s only stale count (218 → 232) was corrected (section C).
- `docs/PUBLICATION_PREFLIGHT.md` (218 tests), `docs/FINAL_SHIPPING_AUDIT.md`
  (218/218 tests, plus a note about a *previously-found* stale "195 tests"
  string), and `docs/MADE_SEARCH_COMPLETENESS_FIX.md` (190 tests) were
  **deliberately left untouched**. These are dated, point-in-time audit
  reports from earlier passes — `PUBLICATION_PREFLIGHT.md` in particular
  explicitly describes an *old* demo state (7 shots / 1 MADE / 3 MISSED / 3
  UNKNOWN, session `3809b2b304064f21`) that this pass's own work has long
  since superseded. Rewriting their numbers to match today would falsify
  the historical record of what those passes actually found, which the
  task explicitly asked to avoid. This report
  (`OVERNIGHT_PUBLICATION_READINESS.md`) is the current source of truth;
  older reports are historical and should be read as dated.
- `docs/METHODOLOGY.md`'s "FormAI Basketball" branding was corrected
  (section C) since it is shipped live into the current demo, not a
  historical record.
- No remaining claims that "the outcome problem was solved" or that
  automatic detection achieves 8/11 were found in current-state docs; the
  README and in-app copy are consistent about outcomes being manually
  verified for the demo specifically.

## P. Production / research separation

Confirmed by direct filesystem scan (not `git grep` — most of this repo is
currently untracked, which would make a `git grep`-based check silently
vacuous): no file under `app/` (excluding `app/research/` itself) references
`app.research`, `apply_verified_outcomes`, or
`VERIFIED_OUTCOMES_BY_SHOT_INDEX`. The verified-outcome overlay exists only
in `scripts/export_demo.py`, confirmed by the same scan and by
`test_d_normal_sessions_never_receive_verified_labels`.

## Q. Security / privacy scan

- `.env` exists at the repo root, is **not** tracked by git, and is covered
  by `.gitignore` (`.env` line). It contains one key
  (`ROBOFLOW_API_KEY`) — confirmed present and non-empty by checking only
  its length, never its value; **the value itself is not reproduced
  anywhere in this report.**
- `git ls-files` (tracked files only) contains no filename matching
  `secret`, `credential`, `apikey`, `api_key`, or `token`.
- `.gitignore` confirmed (via `git check-ignore -v`) to actually cover: the
  RF-DETR checkpoint and YOLO weights (`models/*.pt`, `models/*.pth`),
  `data/datasets/`, `data/training_runs/` (which is where the raw
  `checkpoint_best_*.pth` training artifacts live), the SQLite DB
  (`data/db/*.sqlite3`), uploads/jobs/outputs/logs/diagnostics under
  `data/`, and `.env`.
- Personal Windows path / username search (redacted here; the real
  local username was searched for directly) across all tracked-file-type
  extensions found exactly one legitimate hit:
  `scripts/export_demo.py`'s own `HARD_FORBIDDEN_CONTENT` denylist (the
  literal strings it scans the *export* for, not a leak itself) — this was
  already re-confirmed clean by the export's own privacy scan
  (`PASS -- no forbidden filenames or content patterns found`) on every
  regeneration this pass.
- Three **historical audit docs** (`docs/PUBLICATION_PREFLIGHT.md`,
  `docs/FINAL_SHIPPING_AUDIT.md`, and by extension similar dated reports)
  do contain the real Windows username/path in prose, describing the
  ShuttleSight investigation. These are internal process documents, not
  user-facing product docs — flagged in section R as something to exclude
  from (or redact before) any public publish, not edited here since they
  are historical records (section O's rule applies equally to this).
- No API keys, tokens, or passwords of any kind found in any tracked or
  about-to-be-added file.

## R. Git hygiene + proposed publication file plan

Current `git status` (master, HEAD `b08c2fe`): one pre-existing modified
tracked file (`docs/VIDEO4_EVALUATION_PROTOCOL.md` — modified before this
pass began, left untouched; the user should review this diff before
staging anything), plus a large set of untracked paths (`app/`, `frontend/`,
`scripts/`, `tests/`, `docs/*.md`, `README.md`, `pytest.ini`,
`requirements.txt`, `run.ps1`, `.gitignore`, `ShuttleSight/`).

No untracked file over 2MB was found outside of already-ignored paths and
`ShuttleSight/` (a 451MB nested, unrelated, separately-versioned project —
see section S). `dist/` is correctly ignored and was never a candidate.

**Do not run `git add -A`.** Proposed explicit staging plan for when the
user is ready to publish:

```
git add .gitignore README.md pytest.ini requirements.txt run.ps1
git add app/ frontend/ scripts/ tests/
git add docs/METHODOLOGY.md docs/FINAL_DEMO_GROUND_TRUTH.md \
        docs/SHOWCASE_SEGMENTATION_FIX.md docs/OVERNIGHT_PUBLICATION_READINESS.md
        # (plus any other specific docs/*.md the user wants public --
        # recommend reviewing docs/ file-by-file rather than `docs/` in
        # bulk, since it currently mixes user-facing docs with internal
        # research/audit history, some of which references the real
        # Windows path -- see section Q)
```

`ShuttleSight/` is now also covered by a dedicated `.gitignore` entry added
this pass (belt-and-suspenders on top of "don't add it"), so even a future
accidental broad `add` can no longer sweep it in.

## S. ShuttleSight status

Re-checked, **not moved, not deleted** (per explicit instruction):

- Destination `~\Downloads\ShuttleSight\` (outside this repo, sibling to
  it) is still genuinely empty (only `.`/`..`).
- Nested `<this repo>\ShuttleSight\` still
  has its own `.git` with **zero commits** (`git log` there still reports
  "does not have any commits yet") and all files still untracked within
  that nested repo.
- Safe move procedure (unchanged from the prior pass's finding, re-verified
  here): since the destination exists but is empty, and the source has its
  own uncommitted `.git`, the move is a plain directory move/rename (e.g.
  `Move-Item` or `robocopy /MOVE`) of the *contents* of the source into the
  destination (not the source directory itself, since the destination
  already exists) — this preserves the nested `.git` (and its future
  history) intact, since it's just another file being moved. **Not
  performed this pass, per instruction.**
- Added to `.gitignore` this pass (section R) purely so ArcVision's own git
  history can never accidentally absorb it in the meantime.

## T. RF-DETR checkpoint publication plan

- Path: `models/rfdetr_ball_rim_v1.pth`. Size: **127,473,636 bytes (~127.5
  MB)**.
- This exceeds GitHub's hard 100MB per-file limit for a normal push — it
  **cannot** be committed directly to the repository, with or without
  Git LFS bandwidth concerns aside (it would simply be rejected).
- Already correctly `.gitignore`d (`models/*.pth`).
- App behavior when missing: confirmed by reading
  `app/vision/detection/ball_rim_detector_rfdetr.py` — raises a clear,
  actionable `FileNotFoundError` at construction time naming the expected
  path, explicitly stating there is no generic/COCO fallback (ball/rim
  aren't COCO classes) and pointing at
  `scripts/train_ball_rim_detector.py` to reproduce it. This is honest,
  hard-fail behavior, not silent degradation.
- README already explains this (the "Note on the fine-tuned detector
  checkpoint" section) and suggests either reproducing training or asking
  the maintainer directly.
- **Recommendation** (not performed — distribution is a user decision):
  attach `rfdetr_ball_rim_v1.pth` as a binary asset on a GitHub Release for
  this repo once it exists, and update the README's checkpoint note to link
  directly to that release asset. GitHub Releases support arbitrary binary
  attachments up to 2GB with no LFS setup required, which comfortably fits
  127.5MB.
- License/attribution for the checkpoint itself: it is fine-tuned from
  RF-DETR-Small (Apache-2.0) on the CC BY 4.0 "Basketball Shooting Robot"
  dataset — both already correctly attributed in the README (section N).
  **No license terms are invented here**; if the user wants the checkpoint
  itself to carry an explicit license/attribution notice distinct from the
  code license, that's a decision for the user, not made on their behalf.

## U. ArcVision license readiness — **BLOCKER**

**No `LICENSE` file exists at the repository root** (confirmed:
`find . -maxdepth 1 -iname "LICENSE*"` returns nothing). This is reported as
a blocker, not resolved — per instruction, no license was chosen or added on
the user's behalf. Third-party attribution *is* already handled correctly
in the README (MediaPipe, Ultralytics/YOLOv8n with its own license caveat,
RF-DETR, and the CC BY 4.0 dataset are all named with their own licenses —
section N) — what's missing is a license for ArcVision's *own* code.

## V. GitHub Pages / static-hosting readiness

- `dist/static/js/env.js` correctly forces `window.ARCVISION_MODE = "demo"`
  and carries an empty `ARCVISION_REPO_URL` placeholder pending a real repo
  URL — documented as intentional in the file itself.
- No `localhost`/`127.0.0.1` references anywhere in `dist/`. The only
  `http://` string in any shipped JS is the standard SVG namespace URI in
  `charts.js` (not a network call).
- The only root-absolute (`/api/...`) fetch calls in `api.js`
  (`upload`, `status`, `results`, non-demo `listSessions`) are all either
  explicitly gated behind `if (window.ARCVISION_MODE === "demo")` guards
  that throw/return early instead of firing, or (for `status`/`results`)
  simply never invoked by the demo code path, which uses the separate,
  relative-path `loadDemoSession()` (`fetch("demo/session.json")`) instead.
  None of these execute against a static host in demo mode.
- All actual demo-mode data fetches (`demo/session.json`,
  `demo/methodology.md`, `demo/annotated.mp4`) use **relative** paths, so
  the export works whether hosted at a domain root or a GitHub Pages
  project subpath (`username.github.io/reponame/`).
- `.nojekyll` is present in the export root (prevents GitHub Pages' Jekyll
  processor from mangling the `static/`-prefixed asset paths).
- Refresh/direct-load behavior: not separately re-tested this pass beyond
  the `page.goto(BASE, wait_until="networkidle")` cold-load used throughout
  sections D–H, which is itself equivalent to a fresh direct load (no
  client-side routing state carried over from a prior page).
- **Not deployed.** No GitHub Pages branch was touched, no `gh-pages` push
  occurred.

## W. Screenshot readiness

No screenshots are currently embedded in the README or committed anywhere
as marketing assets. The QA screenshots taken this pass
(`data/diagnostics/browser_qa/*.png`, gitignored under `data/diagnostics/`)
are diagnostic captures, not curated marketing screenshots, but several are
good enough quality/composition to reuse directly. Recommended set for the
README/repo description (all real, no fabricated data):

1. **Landing / hero** — `01_landing_desktop_light.png` (1440×900) or its
   dark-mode counterpart `11_landing_desktop_dark.png`.
2. **Coach** — `04_coach_tab_desktop_light.png` (1440×900) — shows the
   headline stats + coaching narrative + focus card together.
3. **Shots** — `06_shot_detail_desktop_light.png` (1440×900) — shows the
   chip strip plus one expanded shot with the "Verified outcome" badge
   visible (good for explaining the demo's own transparency mechanism).
4. **Replay** — `07_replay_tab_desktop_light.png` (1440×900) — video frame
   with pose/hoop overlay plus the "Jump to shot" panel.
5. **Details** — `09_details_tab_desktop_light.png` (1440×900) — mechanics
   charts.

No new data was fabricated to produce these; they are the same real,
precomputed session used throughout this report.

## X. Performance sanity

- Total export size: 13.85 MB (`demo/annotated.mp4` 11.2MB,
  `static/images/hero-basketball.png` 1.8MB, `demo/session.json` 41KB, all
  JS/CSS combined ~107KB). Nothing oversized or duplicated; no re-encoding
  performed (none needed).
- No blocking `<script>` issues found in `index.html` beyond what a static
  demo of this size already requires.
- No simple, safe optimization was skipped; none was identified as
  necessary this pass.

## Y. Remaining blockers

1. **No LICENSE file** (section U) — the only hard blocker found this
   pass. Needs the user's explicit choice before any public push.
2. **Repo URL placeholder** (`ARCVISION_REPO_URL` in `env.js`, plus the
   README's "link pending" demo placeholder) needs filling in once the
   actual public repo/Pages URL exists — inherently can't be done before
   the repo exists.
3. **Checkpoint distribution** — no GitHub Release exists yet to attach
   `rfdetr_ball_rim_v1.pth` to (can't be created before the repo is public);
   the plan is written (section T) but not executed.
4. **Historical audit docs containing the real Windows path** (section Q) —
   a publishing decision (exclude vs. redact), not fixed here since these
   are preserved historical records, not something to silently rewrite.
5. `docs/VIDEO4_EVALUATION_PROTOCOL.md`'s pre-existing uncommitted
   modification (predates this pass) should be reviewed by the user before
   any `git add`.

## Z. FINAL STATUS

**NOT READY FOR PUBLICATION** — blocked on exactly one item: **no LICENSE
file exists**, and per instruction none was chosen on the user's behalf.

Everything else audited this pass is in a genuinely good, verified state:
232/232 tests passing, two real frontend/export bugs found *and* fixed
(NaN-breaks-JSON; tab-switch-breaks-Methodology) with the fixes verified by
actually re-running the demo in a real browser afterward (not just
re-reading the diff), a third suspected bug (Jump-to-Shot) traced to the
local QA server and disproven, clean production/research separation, no
exposed secrets, `.gitignore` correctly covering all large/private
artifacts (plus a new safety-net entry for the unrelated ShuttleSight
directory), an explicit non-`-A` staging plan for when the user is ready,
and a written (not invented) checkpoint-distribution plan.

All local processes started during this pass (the plain and Range-capable
`http.server` instances on port 8843) have been stopped. No server is
running. The repository is left in a safe, reviewable, uncommitted state —
nothing was staged, committed, pushed, or deployed.
