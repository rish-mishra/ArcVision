# ArcVision Public Demo — Deployment Readiness Audit

Research/planning only — nothing has been implemented or deployed. Grounded in actually
inspecting this repo's real backend routes, the real stored `real_test_01` session, and the
real annotated-video output on disk (not assumptions).

---

## 1. Which parts of the app actually need a backend

Reading `app/api/routes.py` end to end, every route falls into one of two buckets:

| Route | Needs a live backend? | Why |
|---|---|---|
| `POST /sessions/upload` | **Yes** | Runs RF-DETR/tracking/the full pipeline — this is the one thing a static host fundamentally cannot do |
| `GET /sessions/{id}/status` | **Yes** | Polls an in-process job |
| `GET /sessions/{id}/results` | **No** | Just returns a stored JSON blob — a static file *is* this response |
| `GET /sessions` (History list) | **Yes** | Queries the SQLite DB |
| `DELETE /sessions/{id}` | **Yes** | Writes to the DB |
| `GET /sessions/{id}/video/{kind}` | **No** | Just streams a file off disk — a static file *is* this response |
| `GET /methodology` | **No** | Just returns `docs/METHODOLOGY.md`'s text |

Three of seven routes are backend-required (upload, status, history/delete). Four are pure
file-serving that a static host does natively. This is exactly why a static "one pre-baked
session" demo is viable: **Coach, Shots, Replay, and Details all consume only the `results`
payload and a video file — nothing on that path requires a server.**

## 2. Can a real session be exported as static JSON/assets? — Yes, verified

I pulled the actual stored record for `real_test_01` (session `45fe2af33f2340ee`, 7 shots, the
one already backfilled with Stage-4 coaching data):

- `analysis_json` (what `/results` already returns, plus `coaching`): **24,303 bytes**. This is
  a real, unmodified output of the real pipeline — not sample/fabricated data.
- Scanned the full JSON text for local paths, usernames, `.env`/API-key-shaped strings: **found
  nothing**. It's pure measurement data (angles, timestamps, confidences, hoop pixel
  coordinates).
- The route-level fields the frontend also expects (`session_id`, `original_filename`,
  `created_at`, `has_annotated_video`) are trivial to splice on top of the stored JSON in an
  export script — no backend needed to produce them.

**This confirms the frontend's existing `renderDashboard(data)` can be fed this exact static
JSON with zero changes to how Coach/Shots/Details render it.**

## 3. The annotated replay video

Checked the actual rendered files on disk for this session:

- `annotated.mp4`: **4.60 MB**
- `diagnostic.mp4`: **4.71 MB**

This is far smaller than I'd have assumed before checking — small enough that video hosting is
**not actually a constraint** for any free static host (see §4). The existing `<video>` element
and "jump to shot timestamp" behavior in the Replay tab can be pointed at a static file path
with no code changes beyond where the URL comes from.

**Important privacy caveat, not a technical one:** `annotated.mp4` is a re-render of the
**original recorded frames** with overlays drawn on top — it is not a de-identified or
skeleton-only rendering. Publishing it is, in privacy terms, essentially equivalent to
publishing the raw source video: the real footage (you, your surroundings) is fully visible,
just with tracking graphics added. I have not watched the video and cannot judge whether that's
fine — this is a decision only you can make. Options, in order of privacy-conservativeness:
1. **Don't include the video at all** — Replay shows an honest "not included in the public
   demo, available when running locally" state; Coach/Shots/Details remain fully real and
   interactive. Meets "genuine outputs, nothing fabricated" trivially (we simply omit a piece).
2. **Include only `annotated.mp4`** (clean overlay, no debug/diagnostic clutter) — smaller
   exposure surface than also publishing the diagnostic view.
3. **Include both** — matches the full local experience exactly.

I'd default to option 2 unless you've already watched it and are comfortable with it being
public, but this is explicitly your call, not mine.

## 4. Hosting: GitHub Pages vs. alternatives

Given the real numbers above (frontend ~50KB, session JSON 24KB, one video ~4.6MB — total
**under 10MB** for the whole published bundle), every mainstream free static host clears this
with enormous headroom:

| Host | Free tier limits | Fit |
|---|---|---|
| **GitHub Pages** | ~1GB soft repo-size guidance, ~100GB/mo soft bandwidth, HTTPS + custom domain free | Fits with >100x headroom; zero build tooling; a `username.github.io/arcvision` URL reads well on an application |
| Cloudflare Pages | 25MB per asset (free tier), generous bandwidth | Also fits (4.6MB < 25MB) — viable alternative |
| Netlify | 100MB per file (free tier), 100GB/mo bandwidth | Also fits |
| Vercel | Similar free static hosting | Also fits |

**Recommendation: GitHub Pages.** It's the most standard choice for exactly this use case (a
portfolio project already living on GitHub), needs no account beyond the one hosting the repo,
requires no CLI/build step, and is unambiguously, permanently free for a public static site at
this size — there's no credit system, no usage-based billing, no way it "starts charging."

**Publish from a dedicated `gh-pages` branch, not a `/docs` folder on `main`.** This repo's
`main` branch already uses `docs/` for internal engineering reports (METHODOLOGY, the Video 4
evaluation, the architecture-freeze decision) — mixing those with the served site's static
assets in the same folder invites collisions and confusing published-vs-internal boundaries. An
orphan `gh-pages` branch containing only the exported site is the standard, clean pattern.
**Requires a `.nojekyll` file** at the publish root, or GitHub's default Jekyll processing will
try to interpret the site (and can mishandle the `static/` folder name and the JSON asset).

## 5. The 127MB RF-DETR checkpoint — why the demo doesn't need it

The demo never runs inference. It loads one pre-computed `results.json` and plays one
pre-rendered video. The checkpoint (`models/rfdetr_ball_rim_v1.pth`) is a **local-mode-only**
dependency — it stays exactly where it already is (gitignored, never in git, never in any
published branch) and is completely irrelevant to whether the public demo works. This is the
core reason a $0 static demo is viable at all: the expensive artifact never needs to leave your
machine.

## 6. Public GPU inference — investigated, not recommended

You asked me to only recommend this if there's a genuinely practical $0 option. There isn't one
I'd stand behind for a portfolio link that needs to reliably "just work":
- No mainstream host offers a **persistently free GPU** for an always-on public service (free
  GPU tiers that exist, e.g. Hugging Face Spaces' shared/ZeroGPU allocation, are quota-limited,
  cold-start, and not designed for guaranteed-available demo links).
- CPU-only inference (falling back to the generic YOLOv8/YOLO-World stack, since RF-DETR's
  checkpoint shouldn't be published anyway) would be slow enough on a free shared CPU tier to
  produce a poor first-impression wait time for a reviewer — the opposite of the goal.
- It adds real operational risk (the exact "unexpectedly starts charging" or "silently stops
  working" failure modes you explicitly asked me to avoid designing around).

**Verdict: skip it entirely for now.** The static pre-baked demo already fully satisfies "a
reviewer clicks a link and immediately experiences ArcVision" — live public inference adds
complexity and risk for no gain against that actual goal. Worth revisiting only if you later
want live upload as a distinct, separately-justified feature.

---

## Recommended architecture

**One codebase, two modes, distinguished by one small flag — not a fork or a second frontend.**

```
Public demo (gh-pages branch, $0, static)          Local (main branch, unchanged)
─────────────────────────────────────────          ──────────────────────────────
GitHub Pages serves:                                run.ps1 → FastAPI + SQLite +
  index.html (identical file)                         RF-DETR checkpoint (local disk)
  static/js/app.js, api.js, charts.js (identical)    Full upload → process → History
  static/js/env.js  → ARCVISION_MODE = "demo"          flow exactly as it works today
  demo/session.json  (real, exported)
  demo/annotated.mp4 (real, exported)
  demo/methodology.md
```

- `frontend/static/js/env.js` (new, tiny): one line, `window.ARCVISION_MODE = "local"` by
  default in this repo (so a fresh clone + `run.ps1` behaves exactly as it does today, zero
  regression). The exported `gh-pages` copy has this one value changed to `"demo"` — this is the
  **entire** difference between the two published variants of the frontend.
- `api.js` gains: a demo-mode branch in `upload()` that rejects immediately with a clear message
  instead of attempting a network call; a new `loadDemoSession()` that fetches the static JSON;
  a demo-mode branch in `videoUrl()`/`methodology()` pointing at the static files instead of
  `/api/...` routes.
- `app.js` gains: a "Try Demo" button on the landing page (shown only in demo mode); its click
  handler calls `loadDemoSession()` → `renderDashboard()` → `switchView("dashboard")` directly,
  skipping the upload/processing/polling flow entirely since there's nothing to poll. `History`
  and `Upload` show a short, honest "not available in the public demo" message using the
  **existing** error-box UI (Day 1's component, zero new markup needed).
- A new **export script** (`scripts/export_demo.py`, not part of the running app) reads one
  chosen completed session from the real DB, writes `gh-pages-export/demo/session.json` (the
  real `/results` shape, `session_id` replaced with a plain `"demo"` placeholder for a cleaner
  public payload), copies the chosen video(s), copies `frontend/*`, copies
  `docs/METHODOLOGY.md`'s text, and writes `.nojekyll`. Running it does not touch the live app,
  the DB, or any tracked file in `main`.

This is a **presentation/export concern only** — no CV, tracking, outcome, biomechanics, or
coaching-selection code is touched by any of this.

## Exact files/assets needed for the demo bundle

| File | Source | Size |
|---|---|---|
| `index.html`, `static/css/main.css`, `static/js/{app,api,charts}.js`, `static/favicon.svg` | copied as-is from `frontend/` | ~50KB total |
| `static/js/env.js` | new, one line | <1KB |
| `demo/session.json` | exported from session `45fe2af33f2340ee`'s stored `analysis_json` + route-level fields | 24KB |
| `demo/annotated.mp4` | copied from `data/outputs/45fe2af33f2340ee/annotated.mp4` | 4.60MB |
| `demo/diagnostic.mp4` *(optional — see §3)* | same source | 4.71MB |
| `demo/methodology.md` | copied from `docs/METHODOLOGY.md` | ~41KB |
| `.nojekyll` | new, empty file | 0 bytes |

## Expected deployment size

**~4.7MB without the diagnostic video, ~9.4MB with it.** Roughly 1% of GitHub Pages' soft
size guidance. Not a meaningful constraint under any realistic portfolio-review traffic level
(even a generously-estimated 10,000 page loads would only total ~50-100GB, still within the
soft bandwidth guidance, and GitHub Pages doesn't meter or bill for this — it just asks
large/heavy-traffic sites to reconsider their approach).

## Changes required (summary)

1. `frontend/static/js/env.js` — new file, defaults to `"local"`.
2. `frontend/static/js/api.js` — demo-mode branches in `upload`, `videoUrl`, `methodology`; new `loadDemoSession`.
3. `frontend/static/js/app.js` — "Try Demo" button + handler; demo-mode messaging for Upload/History.
4. `frontend/index.html` — one new `<script src="static/js/env.js">` tag + the Try Demo button markup.
5. `scripts/export_demo.py` — new, standalone, run manually/occasionally, never part of the live app.
6. New `gh-pages` branch (or an export directory you push there) — not part of `main`.

Nothing under `app/` changes at all.

## Privacy/security checklist

- [ ] **You've reviewed `annotated.mp4` yourself** and are comfortable with the real footage
      being public (see §3 — I cannot watch video and did not assess this).
- [x] No `.env`, API keys, or credentials anywhere in the export path (export script only ever
      touches `frontend/`, the DB's stored JSON, and one video file).
- [x] `analysis_json` scanned for local paths/usernames — none found.
- [x] The raw local filesystem path to the video (`C:\Users\...`) is never included in the
      `/results` payload today (confirmed by reading `routes.py` — only a boolean
      `has_annotated_video` is exposed) and won't be in the export either.
- [x] RF-DETR checkpoint, training datasets, and raw source `.mov` files are never part of the
      export (the export script only reads the specific chosen session's stored JSON + its
      already-rendered output video).
- [ ] **Decide whether to publish the raw source video files at all** — my recommendation is no
      regardless of the `annotated.mp4` decision above; only derived demo assets are needed.
- [x] `session_id` replaced with a generic placeholder in the exported JSON (cosmetic, not a
      real security boundary, but avoids leaking an internal DB identifier for no reason).

## Step-by-step deployment process (for when you approve implementation)

1. Implement the six changes above on `main` (small, additive, reviewable diff).
2. Run `scripts/export_demo.py` locally → produces a clean export folder.
3. `git checkout --orphan gh-pages`, copy the export folder's contents to the branch root
   (or push the export folder as the branch content directly), commit, push.
4. In the GitHub repo settings → Pages → set source to the `gh-pages` branch, root folder.
5. Visit the generated `https://<username>.github.io/<repo>/` URL, click **Try Demo**, confirm
   Coach/Shots/Replay/Details all render with the real data.
6. Add the live link to `README.md` (top of the file — this is the resume/application payoff).
7. To refresh the demo later (e.g. after a nicer session becomes available): re-run the export
   script, commit the updated `gh-pages` branch, done — no redeploy pipeline needed.

## Limitations of the free/public version (to state honestly, e.g. in the demo UI itself)

- Upload is disabled — it's a fixed, pre-analyzed session, not a live analysis tool.
- History is disabled — there's only the one bundled session.
- No RF-DETR/local pipeline runs anywhere publicly — by design, not a missing feature.
- The Replay video (if included) reflects one specific real session's footage/outcome; it does
  not demonstrate every code path (e.g. it may not showcase an UNKNOWN-heavy or abstained-Coach
  state) — worth noting in the demo's own copy so a reviewer doesn't assume it's the only
  behavior the system has.
- Running the real thing (your own video, live RF-DETR, live Coach) requires the local
  install — the demo's own UI should say this plainly and point at the README.
