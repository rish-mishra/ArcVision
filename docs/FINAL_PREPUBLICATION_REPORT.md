# ArcVision — Final Pre-Publication Report

Unattended final preparation pass, run directly after
`docs/OVERNIGHT_PUBLICATION_READINESS.md`. **Nothing was published, deployed,
pushed, committed, or staged.** No GitHub repository was created. The RF-DETR
checkpoint was not uploaded anywhere. No CV/threshold/detector/tracker/
outcome/biomechanics behavior was modified, and no verified ground-truth
labels were touched. ShuttleSight was inspected only, never moved or
deleted.

**One discrepancy from the task brief, flagged rather than silently
resolved:** the brief named `ab556626332b440e` as "the current approved
final session." That session predates the overnight pass's NaN fix — its
stored `analysis_json` has the bug baked in from before the fix existed, and
re-pointing the export at it would reintroduce the exact problem this pass
verifies is fixed. The export continues to use `fee1c3bcd7b84322` (created
during the overnight pass, under the fixed code, and the session already
verified in `OVERNIGHT_PUBLICATION_READINESS.md`). Both sessions are the
same source video (`arcvision_demo_final.mov`) analyzed by the same frozen
architecture and score identically (11 shots, 8 verified MADE / 3 verified
MISSED / 72.7%) — the only difference is that one has a valid `p_value` and
the other doesn't. This is reported here rather than assumed away; see
section G.

---

## A. MIT LICENSE status

Added: `LICENSE` at the repository root, standard MIT text, year 2026.
Diffed by eye against the canonical MIT template — permission grant,
"AS IS" warranty disclaimer, and liability limitation paragraphs all present
and unmodified from the standard wording.

## B. Copyright holder status — **needs your input**

The copyright line currently reads:

```
Copyright (c) 2026 [COPYRIGHT HOLDER NAME — FILL IN]
```

Not guessed, per instruction. Repo metadata gives two different candidate
names rather than one unambiguous answer:

- `git config user.name` (the identity on both real commits in this repo):
  **`HiRis`**.
- The commit author email, `hirishabh.mishra@gmail.com`, implies a fuller
  real name along the lines of **"Hirishabh Mishra"**, which is a different
  string than the git handle above.

Since those two signals disagreed, this was exactly the "ambiguous — don't
guess" case, and the placeholder was left for explicit resolution rather
than guessed. **Resolved** in the publication pass: the user specified
"Rishabh Mishra" directly, and `LICENSE` now reads
`Copyright (c) 2026 Rishabh Mishra` — see
`docs/ARCVISION_PUBLICATION_REPORT.md` section A.

## C. Third-party attribution status

Added a new `## Licensing` section to the end of `README.md`, distinguishing:

- **A. ArcVision's own source code** — MIT, per section A above, scoped
  explicitly to `app/`, `frontend/`, `scripts/`, `tests/`.
- **B. RF-DETR** — Apache-2.0 (already cited elsewhere in the README; now
  also cross-referenced from Licensing).
- **C. MediaPipe** — Apache-2.0, Google.
- **D. Basketball dataset** — CC BY 4.0, University of Arizona "Basketball
  Shooting Robot" (Roboflow Universe), with the attribution link.
- **E. Model/checkpoint considerations** — the fine-tuned checkpoint
  inherits both RF-DETR's Apache-2.0 terms and the dataset's CC BY 4.0
  attribution requirement; stated explicitly rather than left implicit.
- **F. Other assets/dependencies** — YOLOv8n/YOLO-World (Ultralytics,
  AGPL-3.0, with the existing re-licensing-for-commercial-use caveat
  preserved from the Architecture section) and a pointer to
  `requirements.txt` for everything else, none of which is redistributed as
  part of this repo's own source.

The new section explicitly states ArcVision's MIT license "does not extend
to, replace, or relicense" any of the above, and that no ownership of
third-party work is claimed — matching the instruction precisely. No
license terms were invented for anything; where a project's own license was
unclear this report says so rather than asserting one (nothing came up
unclear this pass — all four dependencies already had a documented license
before this pass, carried over correctly).

## D. Tests before/after

- **Entering this pass:** 232 passed (the overnight pass's baseline).
- **Leaving this pass:** **238 passed**, 0 failed.
- **Why the count changed:** legitimate new regression tests were added for
  the two overnight fixes, which previously had *no* dedicated test
  coverage (the overnight pass fixed both bugs but didn't pin them with
  tests):
  - `tests/test_stats_utils.py` (new file, 2 tests) — reproduces the exact
    degenerate-sample condition that makes `scipy.stats.ttest_ind` return
    NaN (two identical-valued samples), asserts `compare_groups()` now
    returns `p_value=None` instead, and asserts the resulting dataclass
    round-trips through `json.dumps(..., allow_nan=False)`. A second test
    confirms a normal, non-degenerate case still produces a real p-value
    (guards against the fix being too aggressive and silently discarding
    valid values).
  - `tests/test_export_demo.py` (+3 tests) — exercises the new
    `_dump_strict_session_json()` helper directly: rejects a payload
    containing NaN, rejects one containing Infinity, and confirms a clean
    payload both succeeds and round-trips through strict `json.loads`
    (the same parser behavior as the browser's `JSON.parse`).
  - `tests/test_frontend_regressions.py` (new file, 1 test) — there is no
    JS test runner in this project (the frontend is deliberately
    build-tool-free), so this pins the tab-panel-scoping fix at the
    source-text level: parses `initTabs()`'s function body out of
    `app.js` and asserts it never again calls the unscoped
    `document.querySelectorAll(".tab-panel")` pattern that caused the
    original bug, and that the scoping mechanism (`ownedPanels`) is
    present. Real end-to-end behavior for this fix is still verified by
    `scripts/browser_qa.py` against a real browser (section H), which is
    the more meaningful check; this test is a cheap tripwire on top of it.
- No test was deleted, skipped, or weakened to produce a passing count.

## E. NaN fix regression — still correct

- `app/analytics/stats_utils.py`'s `compare_groups()` still contains the
  `math.isnan(p_value) or math.isinf(p_value)` guard added during the
  overnight pass, now covered by `tests/test_stats_utils.py` (section D).
- `scripts/export_demo.py` still refuses to write a NaN/Infinity-containing
  payload — this logic was extracted into a small, directly-testable
  `_dump_strict_session_json()` helper this pass (same behavior, same
  `allow_nan=False` call, same `ExportError` on failure; just no longer
  inlined in `build()`), now covered by 3 dedicated tests (section D).
- The regenerated `dist/demo/session.json` (from session `fee1c3bcd7b84322`,
  see the top-of-report note) contains no literal `NaN`/`Infinity` token
  (checked directly against the raw text) and parses successfully under
  Python's **strict** `json.loads` — confirmed again this pass, not assumed
  from the overnight pass's earlier check.

## F. Methodology/tab fix regression — still correct

- `frontend/static/js/app.js`'s `initTabs()` still scopes its panel
  deactivation to `ownedPanels` (the four dashboard tabs) rather than every
  `.tab-panel` in the document — confirmed by reading the current source
  and by the new regression test (section D).
- Real-browser regression (section H): after navigating through all four
  dashboard tabs, the Methodology page (via the footer "How this works"
  link) still renders its full content, including the verified-outcomes
  transparency note — `methodology_mentions_verified: true`,
  `methodology_render_error: null`, and the panel's computed style shows
  `display: block` / real height (~7500px of real content), not the
  `display: none` / 0-height regression state from before the fix.

## G. Demo integrity

Regenerated `dist/` from session `fee1c3bcd7b84322` (see the top-of-report
note on the `ab556626332b440e` discrepancy) via `scripts/export_demo.py`.
Verified directly against the regenerated `dist/demo/session.json`:

- **Exactly 11 shots**, indices `[1..11]`, unique and contiguous.
- **8 verified MADE, 3 verified MISSED** — `session_summary.made=8`,
  `.missed=3`.
- **72.7% verified FG** — `session_summary.shooting_percentage=72.7`.
- **0 shots showing UNKNOWN as primary where a verified result exists** —
  checked directly: zero shots have a missing/null `verified_outcome`.
- **Raw automatic outcomes preserved separately** —
  `automatic_made=2, automatic_missed=5, automatic_unknown=4,
  automatic_shooting_percentage=28.6`, present alongside (not overwriting)
  the verified numbers on both the summary and every individual shot.
- **No NaN, no Infinity** — checked as literal substrings in the raw file
  text (not just "does `json.loads` happen to work"), neither token present.
- **Valid strict JSON** — `json.loads` succeeds.
- **No stale 13-shot session data** — `DEMO_SESSION_ID` in
  `scripts/export_demo.py` points only at `fee1c3bcd7b84322` (11 shots,
  confirmed); the old 13-shot pre-segmentation-fix session
  (`29c7e751775e4f20`) is not referenced anywhere in `dist/` or in the
  export script.
- **Correct annotated video** — `dist/demo/annotated.mp4`, 11,770,020 bytes,
  confirmed by the DB to be rendered from session `fee1c3bcd7b84322`, which
  is itself sourced from `arcvision_demo_final.mov` (status `completed`,
  duration 98.498s, matching the session JSON's displayed duration).
- **Correct methodology** — `dist/demo/methodology.md` ends with the
  required "About this demo's shot outcomes" transparency note, contains
  zero "FormAI" references (rebranding fix from the overnight pass carried
  through into this regeneration), and four correct "ArcVision" references.

## H. Jump to Shot result — **11/11, plus the full torture pattern: 19/19**

Served with `scripts/range_http_server.py` (the same Range-capable server
validated during the overnight pass) on port 8843 — **not**
`python -m http.server`, per instruction, since that server doesn't
implement HTTP Range requests and makes video seeking silently fail for
reasons unrelated to the app (confirmed directly with `curl -H "Range:
..."` returning `206 Partial Content` from this server, vs. `200`/full-body
from the plain one).

Tested via `scripts/browser_qa.py` (real headless Chromium, not inferred):
the specified pattern (1→11, 11→1, 3→9, 9→4, 4→10→2→8) followed by the full
1→11 sweep — **19 attempts, 19 successful**, each verified by reading
`video.currentTime` back after the click and confirming it landed within 1
second of that shot's real `start_time_sec` (`seek_close_enough: true` on
all 19; `readyState: 4` / `HAVE_ENOUGH_DATA` throughout).

## I. Browser console/network

Across landing, Coach, Shots (+ shot-1 detail), Replay, Details, and
Methodology, plus the full Jump-to-Shot sweep: **zero console errors, zero
page errors.** `network_failures` contains only repeated
`net::ERR_ABORTED GET .../demo/annotated.mp4` entries — the expected,
benign result of `video.currentTime` cancelling an in-flight range fetch
each time a new seek starts (no `4xx`/`5xx` response was ever logged, and
every seek in section H succeeded). Tablet (768×1024) and mobile
(390×844) both show zero horizontal overflow
(`scrollWidth === innerWidth` in both).

## J. README status

- New **first-screenful** paragraph added (what/problem/built/stack/why-
  interesting, ahead of "Try it") without touching the existing "What this
  is not" or "Try it" sections — see section S for the exact diff.
- Test count corrected to 238 (was 218 at the very start of the overnight
  pass, corrected to 232 there, now 238 after this pass's new regression
  tests — each correction reflects a real, re-verified count at the time).
- Install/run instructions re-verified against the actual repo this pass:
  `scripts/setup_env.ps1` and `run.ps1` both exist at the paths the README
  names.
- Checkpoint fallback behavior re-verified against the actual code (not
  just the README's own claim): `app/pipeline/orchestrator.py` checks
  `rfdetr_checkpoint.exists()` **before** constructing
  `RFDETRBallRimDetector` and falls back to the generic YOLO/classical-CV
  stack if it's absent — the detector class's own hard
  `FileNotFoundError` (for anyone constructing it directly, e.g. the
  benchmark/diagnostic scripts) never fires through the normal app path.
  The README's "the app still runs, but automatically falls back..."
  claim is accurate, confirmed by reading both files, not assumed.
- Demo-mode explanation re-read: accurately distinguishes the precomputed
  public demo from the live local pipeline, doesn't claim the verified
  demo outcomes are automatic predictions anywhere.
- New `## Licensing` section added (section C).
- Screenshots section updated from a "pending" placeholder to 5 real,
  embedded images (section K).

## K. Screenshots status

Captured this pass with `scripts/capture_readme_screenshots.py` (Playwright,
against the Range-capable server, viewport-only captures at 1440×900 — not
full-page, since some tabs render many thousands of pixels tall) from the
**real, current, regenerated demo** — no fabricated data, no image
generation, no edited analysis values:

- `docs/screenshots/landing.png`
- `docs/screenshots/coach.png`
- `docs/screenshots/shots.png` (shows Shot 1 expanded, including the
  "Verified outcome" badge alongside the separate automatic-detection row)
- `docs/screenshots/replay.png`
- `docs/screenshots/details.png`

All five embedded in `README.md`'s Screenshots section, replacing the old
"pending, save under docs/screenshots/ as overview.png/shot-detail.png/
replay.png" placeholder (which referenced a directory and file set that
didn't exist yet).

## L. Publication manifest status

`docs/PUBLICATION_MANIFEST.md` created — full allowlist-style categorization
(PUBLIC SOURCE, PUBLIC DOCS, PUBLIC ASSETS, GENERATED DEMO, LOCAL ONLY,
IGNORED, RESEARCH / INCLUDE, RESEARCH / EXCLUDE, MODEL DISTRIBUTION,
SHUTTLESIGHT / NEVER INCLUDE), covering every currently untracked path plus
the 3 already-tracked files. Two docs
(`docs/PUBLICATION_PREFLIGHT.md`, `docs/FINAL_SHIPPING_AUDIT.md`) are
recommended as RESEARCH / EXCLUDE because they contain the real local
Windows username/path and are superseded, dated snapshots of earlier
passes. A third doc that did contain the real path
(`docs/OVERNIGHT_PUBLICATION_READINESS.md`) was redacted in place this pass
(generic `<this repo>` / `~\Downloads\...` phrasing substituted, content
otherwise unchanged) rather than excluded, since its findings are still
current and worth keeping public. Verified clean by re-scanning the file
after editing.

## M. Files over 10 MB

**Zero** public-candidate files exceed 10 MB. Every file over 10 MB found
anywhere in the working tree (checkpoints and training-run artifacts under
`data/training_runs/` and `models/`, raw source recordings at the repo
root, uploaded/diagnostic/output videos under `data/`) falls under LOCAL
ONLY, MODEL DISTRIBUTION, or GENERATED DEMO in the publication manifest —
none are git-add candidates. Within the actual publication-candidate
directories (`app/`, `frontend/`, `scripts/`, `tests/`, `docs/`), the
largest file is `frontend/static/images/hero-basketball.png` at 1.87 MB —
well within normal limits, no action needed.

## N. Model release package plan (not executed)

- Path: `models/rfdetr_ball_rim_v1.pth`.
- Size: 127,473,636 bytes (~127.5 MB) — exceeds GitHub's 100MB hard push
  limit; cannot go through normal git regardless of LFS preference.
- **SHA-256:**
  `15f963e5262072d2127efa83968cdfeaefed578bfc01fcea19b11b3b3d4f3f01`
  (computed directly this pass, verified as exactly 64 hex characters).
- **Recommended release asset name:** `rfdetr_ball_rim_v1.pth` (unchanged —
  matches what `app/config.py`'s `checkpoint_name` expects at
  `models/rfdetr_ball_rim_v1.pth`, so a downloader just drops it in place).
- **Recommended release description** (draft, not published):

  > **RF-DETR-Small fine-tuned for basketball ball/rim detection**
  >
  > Fine-tuned from RF-DETR-Small (Roboflow, Apache-2.0) on the University
  > of Arizona "Basketball Shooting Robot" dataset (Roboflow Universe,
  > CC BY 4.0; 9,612 images / 17,258 boxes, `ball` + `rim` classes). Used
  > by ArcVision as the primary ball/rim detector — one forward pass
  > yields both classes, replacing a 4-model generic fallback stack with a
  > single, faster, far more accurate one (see the main repo README,
  > "Basketball-specific detector (RF-DETR)").
  >
  > **Usage:** download this file and place it at `models/rfdetr_ball_rim_v1.pth`
  > in your ArcVision checkout. Without it, ArcVision automatically falls
  > back to a weaker generic detector stack — it is not required to run
  > the app, only to get the accuracy numbers reported in the README.
  >
  > **License/attribution:** inherits RF-DETR's Apache-2.0 license and the
  > training dataset's CC BY 4.0 attribution requirement. This checkpoint
  > is a derivative fine-tune, not original ArcVision code, and is not
  > covered by ArcVision's own MIT license (see the README's Licensing
  > section).
  >
  > **SHA-256:** `15f963e5262072d2127efa83968cdfeaefed578bfc01fcea19b11b3b3d4f3f01`

- **Not uploaded.** Creating the release requires the GitHub repository to
  exist first — this is step 9 of the publication plan (section T), a
  separate deliberate action after the repo is created and the source is
  pushed.

## O. ShuttleSight isolation

- Destination `~\Downloads\ShuttleSight\` (outside this repo entirely) is
  still genuinely empty.
- The nested `ShuttleSight/` directory inside this repo still has its own
  `.git` with zero commits, all files untracked within that nested repo —
  unchanged from the overnight pass, not touched this pass either.
- `.gitignore`'s `/ShuttleSight/` entry (added during the overnight pass)
  re-verified this pass: `git check-ignore` confirms it (and any
  hypothetical file inside it) is ignored, and it does not appear in
  `git status` at all.
- **Exact safe move procedure for later** (unchanged from the overnight
  pass, re-verified): since the destination already exists but is empty,
  and the source has its own uncommitted `.git`, the correct move is a
  plain directory move of the *contents* of the nested `ShuttleSight/`
  into the existing (empty) destination folder — not a move/rename of the
  `ShuttleSight/` directory itself, since the destination path already
  exists. A plain `Move-Item` (or `robocopy /MOVE`) of the contents
  preserves the nested `.git` intact, since it's just another set of files
  being moved, not a git operation. **Not performed this pass.**
- ArcVision's publication set (per `docs/PUBLICATION_MANIFEST.md`) contains
  **zero** ShuttleSight files — confirmed both by the manifest's explicit
  category and by the clean-clone rehearsal (section Q) actually containing
  no `ShuttleSight/` directory.

## P. Secrets/privacy — **PASS**

- `.env`: present, gitignored, not tracked, contains one key
  (`ROBOFLOW_API_KEY`) — its value was never printed in this report or any
  command output, only its presence and length were checked.
- Full git history (`git log --all -p`, both real commits) scanned for
  API-key/secret/password/token-shaped strings: **zero hits.** Only 3
  files have ever been committed
  (`docs/FINAL_DEMO_FREEZE_RECORD.md`, `docs/FINAL_DEMO_GROUND_TRUTH.md`,
  `docs/VIDEO4_EVALUATION_PROTOCOL.md`), across 2 commits total.
- Public-candidate source directories (`app/`, `frontend/`, `scripts/`,
  `tests/`) scanned for secret-shaped assignment patterns
  (`api_key = "..."`, `password = "..."`, etc.): **zero hits.**
- Personal Windows path/username scanned across the same directories:
  **one hit**, `scripts/export_demo.py`'s own `HARD_FORBIDDEN_CONTENT`
  denylist (the literal strings the export scans *for*, confirmed
  previously and reconfirmed by the clean-clone rehearsal, which copied
  this exact file and still passed a broader absolute-path regex scan with
  zero matches).
- `docs/`: two files (`PUBLICATION_PREFLIGHT.md`, `FINAL_SHIPPING_AUDIT.md`)
  contain the real path in prose — categorized RESEARCH / EXCLUDE in the
  manifest, not published. One more
  (`OVERNIGHT_PUBLICATION_READINESS.md`) had it and was redacted in place
  this pass (section L).
- Private raw videos, datasets, the SQLite database, diagnostics, and
  training-run artifacts: all confirmed still covered by `.gitignore`
  (`data/uploads/`, `data/datasets/`, `data/training_runs/`,
  `data/db/*.sqlite3`, `data/diagnostics/`, `data/logs/`, `data/jobs/`,
  `data/outputs/`, `/*.mov`, `models/*.pt`, `models/*.pth`).
- **No secret value was ever printed into this report or any tool output**
  — every check above reports presence/absence and location only.

**Result: PASS.**

## Q. Clean-clone rehearsal

Built in a temporary directory under this session's scratchpad (outside the
repo, never touched repo history), populated with **exactly** the 181 files
`docs/PUBLICATION_MANIFEST.md`'s PUBLIC SOURCE / PUBLIC DOCS / PUBLIC ASSETS
/ RESEARCH-INCLUDE categories call for (i.e. everything `git status` would
offer to add, minus the two RESEARCH/EXCLUDE docs) — not a full directory
copy with excludes bolted on, but built from the same allowlist the manifest
itself defines.

Verified against the rehearsal copy, inspected as if it were a fresh clone:

- `README.md`, `LICENSE`, `requirements.txt`, `pytest.ini`, `run.ps1`,
  `.gitignore` all present at the root.
- `app/`, `frontend/`, `scripts/`, `tests/`, `docs/` all present with
  real content.
- No `.env`, no `*.sqlite3`, no `ShuttleSight/`, no `models/`, no `dist/`
  present — all correctly absent.
- No absolute Windows user path found anywhere in the rehearsal copy
  (broad regex scan for `<drive>:\Users\<name>`, not just the known
  "HiRis" string) — zero matches.
- **`app.main` imports successfully** and constructs its FastAPI app
  object, with no checkpoint present.
- **Test suite run from the rehearsal copy** (same Python environment/
  installed packages as the main repo, since installing the full ML stack
  fresh was outside this pass's scope; the isolation being tested is the
  *file set*, not the interpreter): **236 passed, 2 skipped.** The 2 skips
  are `tests/test_orchestrator_detector_selection.py`'s two checkpoint-
  dependent cases, each with an explicit, accurate skip reason ("Real
  RF-DETR checkpoint not present in this environment") — a clean, honest
  skip, not a failure or a silent false-pass. This directly confirms the
  README's documented fallback behavior is truthful: the app runs, tests
  run, and only the two tests that specifically require the real
  checkpoint decline to run, with an explanation.
- No imports referenced anything outside the copied file set (the import
  smoke test and the 236 passing tests both exercise real import chains
  through `app/`, and none failed with an import error).

**No real-repo changes were made based on anything found in the
rehearsal** — it passed cleanly, so there was nothing to fix. The temporary
directory was deleted immediately after recording these results; confirmed
gone.

## R. GitHub Pages rehearsal

Re-verified against the freshly regenerated `dist/` (session
`fee1c3bcd7b84322`), served through the same Range-capable server used for
section H:

- No `localhost`/`127.0.0.1` reference anywhere in `dist/` (only match for
  any `http://` string in shipped JS is the standard SVG namespace URI in
  `charts.js`, not a network call).
- No API calls required in demo mode — the three root-absolute `/api/...`
  fetch functions in `api.js` are either gated behind
  `ARCVISION_MODE === "demo"` checks that throw/return early, or (for the
  two never invoked by the demo UI) simply dead code on that path; all
  actual demo data comes from relative fetches (`demo/session.json`,
  `demo/methodology.md`, `demo/annotated.mp4`).
- Relative paths confirmed working — every asset above returned `200` when
  requested through the local server exactly as a browser would request
  them.
- Video works with Range support — section H's 19/19 successful seeks are
  the direct proof; `python -m http.server`'s lack of Range support was
  the overnight pass's own root-cause finding for why this looked broken
  there, deliberately avoided this pass.
- Demo JSON loads, hero loads, methodology loads — all returned `200` and
  were exercised end-to-end by `scripts/browser_qa.py` in section I with
  zero console/page errors.
- Direct initial page load: every `scripts/browser_qa.py` context this
  pass used a fresh browser context and `page.goto(BASE,
  wait_until="networkidle")` — equivalent to a cold direct load, not a
  carried-over SPA navigation state — and all five (landing, Coach, Shots,
  Replay, Details) plus Methodology rendered correctly from that state.
- **Not deployed.** No `gh-pages` branch was touched, nothing was pushed.

## S. Files changed this pass

| File | Change |
|---|---|
| `LICENSE` | New. Standard MIT license, year 2026, placeholder copyright-holder name (section B). |
| `README.md` | Added first-screenful "Built with" paragraph; added `## Licensing` section; corrected test count (232→238, twice, tracking the real count at each point); replaced the "screenshots pending" block with 5 real embedded images. |
| `app/analytics/stats_utils.py` | Unchanged this pass — re-verified only (section E). |
| `scripts/export_demo.py` | Refactored the inline NaN-guard write into a named, directly-testable `_dump_strict_session_json()` helper (same behavior); `DEMO_SESSION_ID` unchanged (still `fee1c3bcd7b84322`, see top-of-report note). |
| `frontend/static/js/app.js` | Unchanged this pass — re-verified only (section F). |
| `tests/test_stats_utils.py` | New file, 2 tests (section D). |
| `tests/test_export_demo.py` | +3 tests for `_dump_strict_session_json()` (section D). |
| `tests/test_frontend_regressions.py` | New file, 1 test (section D). |
| `.gitignore` | Added `/ShuttleSight/`-adjacent `.claude/` entry (Claude Code's own local session lock file, previously excluded only via the untracked `.git/info/exclude`). |
| `docs/screenshots/*.png` | 5 new files — real captures from the live demo (section K). |
| `scripts/capture_readme_screenshots.py` | New file — QA-only screenshot tool, not shipped. |
| `docs/PUBLICATION_MANIFEST.md` | New — full allowlist publication plan (section L). |
| `docs/OVERNIGHT_PUBLICATION_READINESS.md` | Redacted in place (3 lines) to remove the real local path/username while preserving the finding (section L/P). |
| `docs/FINAL_PREPUBLICATION_REPORT.md` | This report — new. |
| `dist/` | Regenerated (gitignored, never committed). |

`data/db/formai.sqlite3` gained no new session this pass (no pipeline run
was executed — `fee1c3bcd7b84322` was already produced during the overnight
pass and reused as-is).

## T. Remaining blockers

1. **Copyright-holder placeholder in `LICENSE`** (section B) — the one
   thing genuinely left for you to fill in; everything else in the license
   text is final.
2. **Repo URL placeholders** — `window.ARCVISION_REPO_URL` in
   `dist/static/js/env.js` and the README's "link pending" demo link both
   need the real URL once the GitHub repo/Pages site exists; inherently
   can't be resolved before that.
3. **Checkpoint distribution** — plan is written (section N), nothing
   uploaded; needs a GitHub Release, which needs the repo to exist first.
4. **`docs/VIDEO4_EVALUATION_PROTOCOL.md`'s pre-existing uncommitted
   modification** (predates both this pass and the overnight pass) —
   still sitting as a working-tree change; review its diff before staging
   anything, since it wasn't authored or reviewed during either
   readiness pass.
5. **The `ab556626332b440e` vs. `fee1c3bcd7b84322` naming discrepancy**
   (top of this report) — not a blocker for the export itself (the current
   export is correct and fully verified), but worth reconciling in your
   own notes so a future session doesn't get confused about which session
   ID is "the" approved one. Recommend treating `fee1c3bcd7b84322` as
   canonical going forward, since it's the one produced under the fixed
   code.

Everything else audited across both passes — tests, demo integrity,
browser behavior, production/research separation, secrets, git hygiene,
ShuttleSight isolation, GitHub Pages readiness — is in a clean, verified
state with no open issues.

## U. Exact publication plan location

The full step-by-step sequence for tomorrow (resolve ShuttleSight if still
needed → review git status → stage only allowlisted files → inspect the
diff → initial commit → create the GitHub repo → add remote → push →
create the model release → configure the repo URL → regenerate `dist/` →
enable Pages → verify the live site → capture final screenshots → update
README if needed → final live smoke test) is written out immediately below,
in this same report, as the last section before the verdict. **Not
executed.**

### Exact sequence for manual execution (review only — do not run unattended)

```
1.  (Optional, whenever convenient) Resolve ShuttleSight per section O's
    procedure -- independent of ArcVision publication, no urgency.

2.  git status                      # confirm current state matches this report
    git diff docs/VIDEO4_EVALUATION_PROTOCOL.md   # review the one pre-existing change

3.  Stage ONLY the allowlist in docs/PUBLICATION_MANIFEST.md, e.g.:
    git add .gitignore LICENSE README.md pytest.ini requirements.txt run.ps1
    git add app/ frontend/ scripts/ tests/
    git add docs/METHODOLOGY.md docs/FINAL_ARCHITECTURE_DECISION.md \
            docs/SHOWCASE_SEGMENTATION_FIX.md docs/VIDEO4_FORENSIC_ANALYSIS.md \
            docs/OVERNIGHT_PUBLICATION_READINESS.md docs/FINAL_PREPUBLICATION_REPORT.md \
            docs/PUBLICATION_MANIFEST.md
    git add docs/screenshots/
    # (plus any RESEARCH/INCLUDE docs/scripts you decide to keep -- see
    # the manifest's full list; explicitly skip PUBLICATION_PREFLIGHT.md
    # and FINAL_SHIPPING_AUDIT.md per RESEARCH/EXCLUDE)
    # Never `git add -A`.

4.  git diff --staged                # read the actual staged diff, not just the file list
    git status                       # confirm nothing unexpected got staged

5.  git commit -m "Initial public commit"
    # (or whatever message you prefer -- this is your call, not scripted here)

6.  gh repo create <name> --public --source=. --remote=origin
    # or create it on github.com and note the URL

7.  git remote -v                    # confirm 'origin' is correct if created manually
    git remote add origin <url>      # only if not already set by step 6

8.  git push -u origin master        # or main, matching your default branch choice

9.  Create a GitHub Release; attach models/rfdetr_ball_rim_v1.pth as a
    release asset using the name/description/checksum drafted in section N
    -- only if you're satisfied with the license/attribution framing there.

10. Fill in window.ARCVISION_REPO_URL in frontend/static/js/env.js (the
    SOURCE file, not dist/) and the README's demo-link placeholder with
    the real repo/Pages URL from step 6/8.

11. .venv\Scripts\python scripts\export_demo.py    # regenerate dist/ with the real URL baked in

12. Push dist/'s contents to a gh-pages branch (or your preferred static
    host) per the existing plan in docs/DEMO_DEPLOYMENT_AUDIT.md.
    Enable GitHub Pages for that branch in repo Settings.

13. Visit the live Pages URL yourself; re-run (or re-derive) the checks in
    section H/I/R against the LIVE site, not just the local rehearsal --
    a real host's Range/CORS/caching behavior can still differ from the
    local server used throughout this report.

14. Re-capture the 5 screenshots (scripts/capture_readme_screenshots.py,
    pointed at the live URL instead of localhost:8843) if you want
    them to reflect the live site rather than the local rehearsal --
    optional, since the current ones are already real, current data.

15. If step 14 was done, re-embed the new screenshots and, if anything
    about the demo changed, re-verify the README's Licensing/checkpoint/
    test-count claims are still accurate.

16. One last live smoke test: load the Pages URL fresh (hard refresh),
    click through Coach/Shots/Replay/Details/Methodology, run the
    Jump-to-Shot pattern from section H once by hand.
```

## V. FINAL VERDICT

**READY FOR YOUR MANUAL PUBLICATION APPROVAL**, with exactly one item that
is yours to fill in before step 5 of the plan above: the copyright-holder
name in `LICENSE` (section B/T-1). Everything else audited this pass and
the overnight pass — 238/238 tests, both prior fixes re-verified with fresh
regression tests and a fresh real-browser pass, demo data integrity, Jump-
to-Shot (19/19), zero console/network errors, licensing/attribution now
complete and accurate, a real clean-clone rehearsal that imports and mostly
passes tests with an honest, explained partial skip, a written (not
executed) checkpoint distribution plan with a computed checksum, confirmed
ShuttleSight isolation, a clean secrets/privacy scan including full git
history, and an explicit non-`git add -A` publication plan — is in a
genuinely good, verified state.

No local server or process was left running; the port-8843 server started
for this pass's browser regression was stopped and confirmed down before
this report was written. The repository remains entirely unstaged and
uncommitted beyond this pass's own file edits.
