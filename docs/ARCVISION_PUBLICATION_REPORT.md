# ArcVision — Publication Report

**PUBLISHED — LIVE AND VERIFIED.** GitHub authentication became available
after the prior pass stopped at that exact blocker; this pass resumed from
there, created the repository, pushed source, published the static demo,
released the model checkpoint as a Release asset, and verified the live
result end to end — not just locally.

## A. LICENSE holder

`Copyright (c) 2026 Rishabh Mishra` — unchanged from the prior pass,
re-confirmed as rendered by GitHub itself:
`gh api repos/rish-mishra/ArcVision/license` reports `spdx_id: "MIT"`, and
the raw file on the `master` branch reads exactly that copyright line.

## B. Initial test result

**265 passed**, confirmed at the start of this pass before any further
action (matching the exact baseline stated in the resume instructions).

## C. Final test result

**265 passed** — unchanged. The only source change this pass
(`scripts/export_demo.py`'s hardcoded repo-URL literal, plus two README
link edits) has no test coverage of its literal string value by design
(the existing `test_write_env_js_produces_demo_mode` checks mode, not the
URL) and none of it touched analysis/outcome/CV code.

## D. Files committed

Two follow-up commits this pass, both from an explicit, reviewed diff —
no blind `add`:

- `scripts/export_demo.py` — one line, the hardcoded empty
  `ARCVISION_REPO_URL` literal replaced with the real repo URL.
- `README.md` — the "link pending" demo placeholder replaced with the
  live Pages URL; the checkpoint note's "ask the maintainer directly"
  replaced with a direct link to the `model-v1` Release.

Plus the static demo bundle itself, republished to the orphan `gh-pages`
branch (not `master` — a separate, single-purpose commit containing only
the 12 files `scripts/export_demo.py` produces, built in an isolated `git
worktree` so it could never accidentally pick up any `master`-branch file
that isn't part of the export).

## E. Commit hash(es)

`master`: `fa9ee0d` → `b08c2fe` → `a9a880a` → `d31e32a` (prior pass) →
`f248e6f` (repo-URL literal) → `8adec42` (README live links, current
`HEAD`).
`gh-pages`: `0f24731` (single root commit, "Publish ArcVision static
demo").

## F. Repository name

`ArcVision` — created exactly as specified; the name was available
(confirmed via `gh repo view rish-mishra/ArcVision` returning "not found"
immediately before creation), so no fallback naming decision was needed.

## G. Repository URL

**https://github.com/rish-mishra/ArcVision**

## H. Branch

`master` is the default/source branch (tracks `origin/master`).
`gh-pages` is a second, orphan branch holding only the published static
site — the standard GitHub Pages pattern, matching the plan already
written in `docs/DEMO_DEPLOYMENT_AUDIT.md` from an earlier pass.

## I. Remote verification

`git remote -v` → `origin  https://github.com/rish-mishra/ArcVision.git`
(fetch and push), verified *before* the first push, not after. Confirmed
against the actual GitHub API (not just a local assumption) via
`gh api repos/rish-mishra/ArcVision/git/trees/master?recursive=true`:
209 entries, including `README.md`, `LICENSE`, `.gitignore`, 74 files
under `app/`, 32 under `docs/`, 12 under `frontend/`, 52 under `scripts/`,
28 under `tests/` — and zero matches for `.env`, `shuttle`, any `.pth`/
`.pt` under `models/`, `sqlite`, or any root-level `.mov` file.

## J. README verification

Checked against the actual repo content via API, not assumed:
`gh api repos/rish-mishra/ArcVision/readme` resolves; all 5 README image
`src` paths (`docs/screenshots/{landing,coach,shots,replay,details}.png`)
independently confirmed reachable at
`https://raw.githubusercontent.com/rish-mishra/ArcVision/master/...` —
every one returned `200`. The live-demo link and the checkpoint-release
link added this pass both independently curl-verified at `200`.

## K. Screenshots verification

All 5 `docs/screenshots/*.png` files present in the pushed tree (section
I) and individually confirmed loadable (section J) — not merely "listed in
the tree."

## L. Checkpoint committed to normal git?

**NO.** Re-verified this pass, on the actual pushed remote (not just
locally): `git ls-tree` equivalent via the GitHub API tree listing
(section I) contains no `.pth`/`.pt` file anywhere under `models/`, and a
targeted GitHub code search
(`gh api "search/code?q=repo:rish-mishra/ArcVision+ROBOFLOW_API_KEY"`) —
used as a second, independent confirmation that even a *reference* to a
secret-shaped name isn't indexed in the repo — returned zero results.

## M. Model release status

**Created and verified.** `https://github.com/rish-mishra/ArcVision/releases/tag/model-v1`,
titled "ArcVision RF-DETR Ball/Rim Model v1", with
`rfdetr_ball_rim_v1.pth` attached as a release **asset** (never committed
to git history — see section L). Verified genuinely downloadable, not just
"present in the API response": the asset was actually downloaded fresh to
a temporary directory and its SHA-256 recomputed, matching exactly (see
section N), then the temporary copy was deleted.

## N. Checkpoint SHA-256

```
15f963e5262072d2127efa83968cdfeaefed578bfc01fcea19b11b3b3d4f3f01
```

Computed fresh from the local `models/rfdetr_ball_rim_v1.pth` immediately
before upload (matched the prior pass's recorded value exactly, per the
resume instruction's "expected previous SHA begins 15f963e52" check — no
STOP condition triggered), **and** recomputed a second time from the
downloaded release asset after upload — identical both times. Size:
127,473,636 bytes, matching the GitHub API's reported asset size exactly.

## O. GitHub Pages URL

**https://rish-mishra.github.io/ArcVision/**

Deployed from the `gh-pages` branch, path `/` — confirmed via
`gh api repos/rish-mishra/ArcVision/pages`: `"source":{"branch":"gh-pages","path":"/"}`,
`"status":"built"` (polled until this state was reached, not assumed).
Built from the exact `dist/` output of the final `scripts/export_demo.py`
run this pass (which itself picked up the newly-corrected `ARCVISION_REPO_URL`)
— not a stale build from an earlier pass.

## P. Live demo totals

Checked against the actual deployed site's `demo/session.json`
(`https://rish-mishra.github.io/ArcVision/demo/session.json`, `200`) via a
real browser: **11 shots, 8 verified MADE, 3 verified MISSED, 72.7%
verified FG**, automatic totals preserved separately and unchanged
(`automatic_made=2, automatic_missed=5, automatic_unknown=4`), 0 verified
UNKNOWN.

## Q. Live Jump-to-Shot X/19

**19/19.** Full `scripts/browser_qa.py` sweep re-run against the live
Pages URL (not localhost) — the specified torture pattern
(1→11→3→9→4→10→2→8) plus the full 1→11 sweep, every attempt's
`video.currentTime` read back and confirmed within 1 second of that
shot's real timestamp. Confirmed the live host actually serves HTTP Range
requests (`curl -H "Range: bytes=0-100" .../annotated.mp4` → `206 Partial
Content`, `Accept-Ranges` behavior native to GitHub Pages) — this was the
exact mechanism the overnight pass found broken under a plain
`python -m http.server`, so it was checked directly against the real host
rather than assumed to "just work" because it worked locally under the
Range-capable test server.

## R. Desktop QA

Live, 1440×900: landing (hero, tagline, branding, nav all correct),
Coach (11/8/3/72.7% headline, focus card, evidence), Shots (11 shots,
verified MADE/MISSED, mechanics table), Replay (video loads, plays,
annotated overlay visible), Details (Mechanics 2-column chart grid,
Makes vs Misses, Consistency, Trends), Methodology (loads,
`methodology_mentions_verified: true`) — all confirmed via the live
`scripts/browser_qa.py` run and directly-inspected screenshots
(`data/diagnostics/live_details.png`, `live_shot9.png`).

## S. Mobile QA

Live, 390px: zero horizontal overflow on both landing and Details
(`document.body.scrollWidth === window.innerWidth === 390` exactly, both
pages) — Details is the page most likely to regress here (the
`metric-chart-grid`'s `minmax(min(420px,100%),1fr)` fix from the visual
design pass), re-confirmed working live, not just locally.

## T. Dark/light QA

Live dark mode screenshotted directly
(`data/diagnostics/live_dark_landing.png`, `live_dark_coach.png`):
correct deep-neutral background, readable contrast, the Coach focus
card's left-border accent renders correctly, headline stats
(11/8/3/72.7%) legible. Light mode confirmed via the primary desktop QA
in section R (default color scheme). No color/token changes were made
this pass, so this is a live re-confirmation of the prior visual-design
pass's already-verified result, not a new design check.

## U. Console/network result

Zero console errors, zero page errors, live. The only `network_failures`
entries are the same benign `net::ERR_ABORTED` messages on
`annotated.mp4` from seek-cancellation already explained and re-confirmed
harmless in every prior pass (no `4xx`/`5xx` ever logged; all 19
Jump-to-Shot seeks still succeeded — section Q).

## V. Methodology transparency

Confirmed live: `methodology_mentions_verified: true`; the transparency
note explaining that outcomes were manually verified while detection/
tracking/biomechanics/coaching remain automatic is present and reachable
via the footer "How this works" link on the actual deployed site.

## W. Secret/privacy result

**PASS**, checked against the actual public repository via the GitHub
API (not only local git), across both published branches:

- `master` branch tree (209 entries): no `.env`, no `shuttle`, no
  `models/*.pth`/`*.pt`, no `sqlite`, no root-level `.mov`.
- `gh-pages` branch tree (12 entries): exactly the intended static export,
  nothing else.
- GitHub code search for the API-key environment-variable name: zero
  results.
- The RF-DETR checkpoint is public **only** as a deliberately-attached
  Release asset (section M), never in git history.

No secret value has been printed in this or any prior report at any
point — only presence/absence, location, and (for the checkpoint, which
isn't a secret) its checksum.

## X. ShuttleSight exclusion

**Confirmed absent** from both published branches' trees (section W) and
from `git log --all --name-only` locally. The nested `ShuttleSight/`
directory on disk was not moved, deleted, touched, or referenced by any
command this pass.

## Y. Remaining limitations/blockers

None blocking. Two small, optional items worth noting rather than acting
on unprompted (per "do not make any additional ArcVision improvements"
once checks pass):

- `docs/screenshots/before/`, `docs/screenshots/after/`, and the two
  RESEARCH/EXCLUDE historical audit docs
  (`PUBLICATION_PREFLIGHT.md`, `FINAL_SHIPPING_AUDIT.md`) remain
  deliberately untracked locally, exactly as categorized in the prior
  pass — not a blocker, a standing content decision.
- The live Pages URL and checkpoint Release are both now linked from
  README; no other placeholder-shaped text was found remaining in any
  current-state (non-historical) document during this pass's checks.

## Z. FINAL STATUS

**PUBLISHED — LIVE AND VERIFIED**

- Repository: https://github.com/rish-mishra/ArcVision
- Live demo: https://rish-mishra.github.io/ArcVision/
- Model release: https://github.com/rish-mishra/ArcVision/releases/tag/model-v1
