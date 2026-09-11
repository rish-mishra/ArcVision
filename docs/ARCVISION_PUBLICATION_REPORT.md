# ArcVision — Publication Report

Publication pass. **Local publication steps completed and verified.
Remote publication (GitHub repository creation, push, Pages, model
release, live QA) is blocked** on a hard external prerequisite — no GitHub
CLI/authentication is available in this environment — and was stopped
there rather than improvised around, per explicit instruction. Exact manual
steps to unblock it are given below (section Y) alongside the full,
unexecuted command sequence.

## A. LICENSE holder

`LICENSE` finalized:

```
Copyright (c) 2026 Rishabh Mishra
```

Verified against the canonical MIT template — permission grant, "AS IS"
warranty disclaimer, and liability-limitation paragraphs all present and
unmodified. No remaining placeholder anywhere in a current-state,
about-to-be-published file (`README.md`, `LICENSE`) — confirmed by a
repo-wide grep for `COPYRIGHT HOLDER`/`FILL IN`. The only other places the
string "HiRis" or the placeholder text still appear are
`docs/FINAL_PREPUBLICATION_REPORT.md` (a dated process report documenting
*how* this ambiguity was resolved — updated in this pass with a short
resolution note rather than rewritten) and `scripts/export_demo.py`'s own
`HARD_FORBIDDEN_CONTENT` privacy-scan denylist (the literal string it
scans the export *for*, not a leak). Third-party components were **not**
relicensed — README's existing Licensing section (RF-DETR/Apache-2.0,
MediaPipe/Apache-2.0, the training dataset/CC BY 4.0, YOLOv8n-YOLO-World/
Ultralytics AGPL-3.0) is unchanged.

## B. Initial test result

**265 passed**, matching the expected baseline exactly, confirmed before
any staging began.

## C. Final test result

**265 passed** — unchanged, re-confirmed after the commit (section E) with
no further source changes made in this pass (LICENSE and this report are
the only edits; LICENSE has no test coverage of its own content by design,
and this report is documentation).

## D. Files committed

**183 files**, all from an explicit, human-readable path list (built from
`docs/PUBLICATION_MANIFEST.md`'s allowlist plus this pass's own
categorization of files created since that manifest was written — see
below), staged with `git add --pathspec-from-file=<list>` — **never**
`git add -A` or `git add .`. Full list printed and reviewed before staging
(183 shown in the commit; 2 more files in the 185-line proposed list —
`docs/FINAL_DEMO_FREEZE_RECORD.md` and `docs/FINAL_DEMO_GROUND_TRUTH.md` —
were already committed with identical content, so staging them was a
no-op).

New-since-manifest files, categorized in this pass:

- `docs/CHART_VERIFIED_OUTCOME_FIX.md`, `docs/CHART_MISSING_MEASUREMENT_NOTE.md`,
  `docs/FINAL_VISUAL_DESIGN_PASS.md` — **included** (PUBLIC DOCS, same
  category as the other process reports already in the manifest).
- `docs/screenshots/before/*.png`, `docs/screenshots/after/*.png`,
  `docs/screenshots/before/BEFORE_FILE_HASHES.txt`,
  `docs/screenshots/before/frontend_backup/*` — **excluded**. These are
  the visual-design pass's own before/after review evidence and a
  file-level revert backup — useful for the user's own comparison during
  that pass (already reviewed and approved), not intended as permanent
  public repo content, and redundant with the 5 curated
  `docs/screenshots/*.png` already used by the README. Left as untracked
  local files; not deleted.

Full staged-content audit performed before committing: `git diff --cached
--stat`/`--name-only` reviewed for size and path patterns (largest text
diff ~1500 lines, both binary assets under 2MB and exactly the ones
expected — the hero photo and one README screenshot); grepped the actual
diff content for secret-shaped assignments, personal absolute paths, and
"HiRis" specifically — every hit traced to an already-known-safe source
(the export-time denylist string, or historical process-report prose).
`ShuttleSight` confirmed absent from the staged tree and from the commit's
file list.

## E. Commit hash(es)

`a9a880a` — "Prepare ArcVision for public release" (message used exactly
as suggested), on top of the pre-existing `b08c2fe`/`fa9ee0d` ground-truth
freeze commits. Nothing was squashed, rebased, or force-pushed; history is
purely additive.

## F. Repository name

**Not created.** Intended name: `ArcVision` (per instruction; see section
Y for what to do if that exact name turns out to be taken).

## G. Repository URL

**None yet** — no repository exists remotely.

## H. Branch

`master` (existing local branch; no branch changes made this pass).

## I. Remote verification

**Not applicable — no remote exists.** `git remote -v` returns nothing,
confirmed both before and after the commit in this pass.

## J. README verification

Not yet checked *on GitHub* (nothing is pushed). Locally, README was
re-read this pass for the finalized LICENSE holder line and confirmed
consistent with the Licensing section's wording ("ArcVision's own source
code... MIT License").

## K. Screenshots verification

Not yet checked *on GitHub*. Locally, `docs/screenshots/{landing,coach,
shots,replay,details}.png` are staged and committed exactly as referenced
by README's `![...]("docs/screenshots/...")` embeds from the visual-design
pass.

## L. Checkpoint committed to normal git?

**NO.** Confirmed multiple ways: `models/rfdetr_ball_rim_v1.pth` does not
appear in the 185-line proposed staging list, does not appear in
`git diff --cached --name-only`, does not appear anywhere in
`git log --all --name-only` across all 3 commits, and is covered by
`.gitignore`'s `models/*.pth` rule (`git check-ignore` confirmed). It
remains local-only, exactly as required.

## M. Model release status

**Not created — blocked on the same GitHub-authentication prerequisite as
the repository itself** (a Release is a property of a GitHub repository
that doesn't exist yet). Redistribution rights *are* sufficiently
documented to proceed once a repository exists: the checkpoint is a
fine-tune of RF-DETR-Small (Apache-2.0) on the CC BY 4.0 "Basketball
Shooting Robot" dataset, both already correctly attributed in README's
Licensing section from an earlier pass — no license question is
outstanding, only the mechanical step of having a repo to attach the
Release to. The full prepared release description (name, body, checksum)
is repeated in section Y for direct use once unblocked.

## N. Checkpoint SHA-256

Recomputed fresh this pass (unchanged from the prior pass's value,
confirming the file hasn't moved or been altered):

```
15f963e5262072d2127efa83968cdfeaefed578bfc01fcea19b11b3b3d4f3f01
```

Size: 127,473,636 bytes (~127.5 MB) — `models/rfdetr_ball_rim_v1.pth`.

## O. GitHub Pages URL

**Not deployed — blocked**, same prerequisite. No workflow/Pages
configuration exists yet since no repository exists.

## P. Live demo totals

**Not checked live** (no live site exists). Re-verified locally,
immediately before staging, against the actual `dist/demo/session.json`
one final time: 11 shots, 8 verified MADE, 3 verified MISSED, 72.7%
verified FG, 0 verified UNKNOWN, automatic totals preserved separately
(`automatic_made=2, automatic_missed=5, automatic_unknown=4`), zero
mismatches against the frozen ground-truth table, strict `json.loads`
succeeds (no `NaN`/`Infinity`), global misleading-UNKNOWN warning absent
(`payload["warnings"] == []`).

## Q. Live Jump-to-Shot X/19

**Not applicable to a live site yet.** Local, final pre-publication run
(Range-capable server, real headless Chromium, the specified torture
pattern plus the full 1→11 sweep): **19/19** successful, `seek_close_enough:
true` on every attempt.

## R. Desktop QA

Local only this pass (re-run of `scripts/browser_qa.py` against the exact
`dist/` about to be published): landing, Coach, Shots, Replay, Details,
Methodology all render correctly; zero console errors, zero page errors.

## S. Mobile QA

Local only this pass: 390px viewport, zero horizontal overflow
(`scrollWidth === innerWidth === 390`), confirmed as part of the same
`scripts/browser_qa.py` run.

## T. Dark/light QA

Not re-captured fresh in this pass specifically (no source/CSS changes
were made here beyond `LICENSE`, which has no visual surface) — the
dark/light verification from the immediately preceding visual-design pass
(`docs/FINAL_VISUAL_DESIGN_PASS.md` sections I/J, and the follow-up chart
passes' dark-mode Shot 9 checks) stands unchanged, since the `dist/` being
published in this pass is byte-identical to the one those passes already
verified.

## U. Console/network result

Zero console errors, zero page errors, in the final local
`scripts/browser_qa.py` run (section R). The only `network_failures`
entries are the same benign seek-cancellation `net::ERR_ABORTED` messages
on `annotated.mp4` already explained and re-confirmed harmless in every
prior pass's report (no `4xx`/`5xx` ever logged; every Jump-to-Shot seek
still succeeds).

## V. Methodology transparency

Confirmed present: `methodology_mentions_verified: true` in the final
local QA run; the exported `demo/methodology.md` still ends with the "About
this demo's shot outcomes" note explaining that outcomes were manually
verified while detection/tracking/biomechanics/coaching remain automatic.

## W. Secret/privacy result

**PASS.** Full git-history scan (`git log --all -p`, now 3 commits) for
API-key/secret/password/token-shaped strings: zero real hits (one
documentation sentence *describing* the pattern searched for, not an
instance of it). `.env` confirmed untracked and gitignored, value never
printed. Staged-diff-specific scan (section D) also clean. No secret value
has ever been printed in this or any prior report — only presence/absence
and location.

## X. ShuttleSight exclusion

**Confirmed absent** from the staged tree, the commit's file list, and
`git log --all --name-only` across all 3 commits. The nested
`ShuttleSight/` directory (its own separate `.git`, zero commits) was not
moved, deleted, or modified — untouched, exactly as required. Its
`.gitignore` entry (`/ShuttleSight/`, added in an earlier pass) remains in
place as a standing safety net for any future publication attempt too.

## Y. Remaining limitations/blockers

**One hard blocker, stopping every remote-facing phase of this pass:**

> No GitHub CLI (`gh`) is installed or on `PATH` in this environment
> (confirmed: `which gh` / `where gh.exe` both find nothing), and no other
> GitHub API credential is available to this session. Creating a
> repository requires either the `gh` CLI or a manual action in the
> GitHub web UI — neither of which this session can do on your behalf
> without one of those. Per instruction, this stops the remote-publication
> portion here rather than improvising around it (e.g., attempting an
> interactive credential-manager browser-auth flow unattended, which would
> likely hang or fail silently, or guessing at API tokens).

Everything downstream of repository creation (push, Pages, model release,
all live QA) is blocked transitively by this one thing, not by any
additional separate issue.

**Exact steps for you to unblock and complete publication** (nothing below
was executed):

```powershell
# 1. Install and authenticate the GitHub CLI (one-time), OR create the
#    repo manually at https://github.com/new and skip straight to step 3
#    with the URL it gives you.
winget install --id GitHub.cli
gh auth login

# 2. Create the repository (from this repo's root)
gh repo create ArcVision --public --source=. --remote=origin `
  --description "Basketball shot analysis using computer vision, pose estimation, and biomechanics."
# If "ArcVision" is taken, STOP and tell me rather than picking an
# alternate name yourselves -- per the original instruction, that's your
# call, not mine to improvise.

# 3. If step 2's `gh repo create` didn't already add the remote (e.g. you
#    created it manually in step 1's alternate path):
git remote add origin https://github.com/<your-username>/ArcVision.git
git remote -v   # verify before pushing

# 4. Push
git push -u origin master

# 5. Verify remotely: open the repo URL, confirm README renders with its
#    5 screenshots, LICENSE shows "Rishabh Mishra", source/docs are
#    present, and nothing unexpected is there (no .env, no ShuttleSight,
#    no checkpoint, no raw videos).

# 6. Fill in the real repo/Pages URL where a placeholder exists:
#    - frontend/static/js/env.js: window.ARCVISION_REPO_URL = ""
#    - README.md's "link pending" demo-link placeholder
#    Then regenerate the export and re-verify tests before committing:
.venv\Scripts\python scripts\export_demo.py
.venv\Scripts\python -m pytest -q
git add frontend/static/js/env.js README.md
git commit -m "Add public repository/demo URL"
git push

# 7. Model release (only after the repo exists) -- attach the checkpoint
#    as a Release ASSET, never to normal git history:
gh release create checkpoint-v1 models/rfdetr_ball_rim_v1.pth `
  --title "ArcVision RF-DETR ball/rim checkpoint v1" `
  --notes @'
RF-DETR-Small fine-tuned for basketball ball/rim detection.

Fine-tuned from RF-DETR-Small (Roboflow, Apache-2.0) on the University of
Arizona "Basketball Shooting Robot" dataset (Roboflow Universe, CC BY 4.0;
9,612 images / 17,258 boxes, ball + rim classes). Used by ArcVision as the
primary ball/rim detector.

Usage: download this file and place it at models/rfdetr_ball_rim_v1.pth in
your ArcVision checkout. Without it, ArcVision automatically falls back to
a weaker generic detector stack -- it is not required to run the app, only
to get the accuracy numbers reported in the README.

License/attribution: inherits RF-DETR's Apache-2.0 license and the
training dataset's CC BY 4.0 attribution requirement. This checkpoint is a
derivative fine-tune, not original ArcVision code, and is not covered by
ArcVision's own MIT license.

SHA-256: 15f963e5262072d2127efa83968cdfeaefed578bfc01fcea19b11b3b3d4f3f01
'@
# Then verify the asset downloads and its SHA-256 still matches.

# 8. GitHub Pages -- publish dist/ to a gh-pages branch (per the existing
#    plan in docs/DEMO_DEPLOYMENT_AUDIT.md), enable Pages on that branch
#    in repo Settings, then re-run the browser QA against the LIVE URL
#    (not localhost) -- Range/CORS/caching behavior can differ from a
#    local server even when the file bytes are identical.

# 9. Once live: re-run sections P-U of this report's checklist against
#    the real Pages URL and update this file (or a short follow-up note)
#    with the live results before calling publication complete.
```

## Z. FINAL STATUS

**NOT PUBLISHED — blocked on GitHub CLI/authentication being unavailable
in this environment.**

Everything within this session's control is done and verified: LICENSE
finalized with the exact requested holder, full baseline re-confirmed
(265/265, strict demo JSON, secrets, manifest, ShuttleSight), an explicit
non-`-A` staging plan reviewed file-by-file before staging, a clean
publication commit (`a9a880a`) with the staged content itself audited
before and the resulting history audited after, and the checkpoint
correctly kept out of normal git with its distribution plan fully
prepared and ready to execute the moment a repository exists. The repo is
committed and ready to push the instant you (or a future session with
`gh` available) complete step 1 above.
