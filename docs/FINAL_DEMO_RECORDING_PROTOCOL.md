# Final Demo Recording Protocol — Precommitted Before the Video Exists

**Status when this document was written:** the video described here does not exist yet. Nothing
in this document was reverse-engineered from a result, and no production code was touched to
produce it. It exists specifically so that tomorrow's recording, ground-truth logging, and
evaluation happen in an order that can't be quietly adjusted after the fact.

**Reference points, both already real and already recorded:**
- Current showcase attempt (`arcvision_demo_01`, session `3809b2b304064f21`): 7 detected / 1 MADE
  / 3 MISSED / 3 UNKNOWN.
- V1 fallback (`real_test_01`): 7 detected / 2 MADE / 5 MISSED / 0 UNKNOWN.
- V4 remains, unconditionally, the honest frozen generalization evaluation
  (`docs/VIDEO4_EVALUATION_PROTOCOL.md` / `docs/VIDEO4_FORENSIC_ANALYSIS.md`) — nothing in this
  document changes that, regardless of which video ends up as the interactive demo.

The production pipeline is frozen. This document does not propose, hint at, or leave room for any
threshold, detector, tracker, outcome, biomechanics, or coaching change based on tomorrow's
recording.

---

## 1. Recording setup

Grounded in ArcVision's own already-documented input assumptions (`app/config.py`'s
`VideoConfig`: `.mp4`/`.mov`/`.m4v`/`.avi`, 1.5–300s, up to 500MB) and the same recording
principles already used for V1–V4 and the current showcase video — not invented for this
recording, and not chosen to make any known threshold pass.

- **Orientation: landscape.** Every prior video (V1–V4, the current showcase) was landscape; a
  basketball court scene needs the width to fit shooter and hoop side by side, which portrait
  won't give you.
- **Resolution/FPS: whatever your phone's normal default video mode is** — typically 1080p at
  30 or 60fps. Don't seek out a specific setting; ArcVision downsamples for analysis regardless of
  source resolution/frame rate, so this is about ordinary capture quality, not a tuned target.
- **Camera: stationary.** Tripod, or propped securely against something solid, for the entire
  session. No panning, no tilting, no walking with it.
- **Angle: side or ~45° to the hoop** — the same framing already used for V1–V4, not straight-on
  from under the backboard and not from directly behind the shooter.
- **Distance: roughly 20–30 ft back** (matching the app's own existing on-screen guidance) — close
  enough that the shooter's full body and the hoop both stay clearly resolved, far enough that
  normal movement doesn't risk either leaving frame.
- **Digital zoom: avoid it.** Move physically closer instead if you need to. Digital zoom crops and
  upscales, which reduces exactly the detail (ball edges, rim) detection depends on — a general
  capture principle, not specific to this app.
- **Shooter visibility:** full body in frame, including feet, for the entire shooting motion (load
  through follow-through) — cropping the legs or the top of a jump removes signal this pipeline
  documents itself as depending on.
- **Hoop visibility:** in the same frame as the shooter, continuously, for the whole session — not
  just when the ball is near it.
- **Ball visibility:** no requirement beyond normal, unobstructed daylight/gym visibility — don't
  do anything special to make the ball more or less visible than it naturally is.
- **Lighting:** whatever is realistic and convenient. Don't engineer it to help or hurt the result
  either way. Avoid strong backlighting (a light source directly behind the hoop or shooter,
  silhouetting them) — this is a general CV visibility principle, not a tuned rule.
- **Background:** no special requirement — an ordinary court/driveway background is fine. Avoid
  anything that would visually confuse a "basketball"-shaped or "hoop-ring"-shaped object right
  near the actual ball/hoop (e.g. another ball, a hoop-shaped decoration) if easily avoidable.
- **Other people:** no one else in frame. Single shooter, single ball — the pipeline's documented
  scope, and the same constraint already used for every prior recording.
- **One continuous take, one file.** No cuts, no edits, no re-encoding after recording — raw
  camera output.

## 2. Shot pacing

A simple, repeatable, natural rhythm — not derived from any internal ArcVision timing constant:

```
prepare (ball in hands, get set)
  → pause (stand still, no motion, ready)
  → shoot
  → allow the COMPLETE flight and rim interaction to play out on camera (don't look away, don't
    let anything block the view of the ball reaching the rim/net/floor)
  → allow the result to fully settle (ball comes to rest, or is clearly done bouncing/rolling)
  → retrieve the ball at a normal, natural pace
  → return to shooting position
  → pause / reset (a clear, deliberate stop)
  → next shot
```

**Recommended pause between completed reset and the next attempt: a clear, deliberate 2–3 seconds
of standing completely still** before beginning the next shot's set-up — about the same brief,
natural reset a shooter takes between free throws. This is a plain visual-separation principle
(a clean pause between two distinct events is easier for any motion-based system, human or
algorithmic, to tell apart than two events that blend together) — it was chosen for that reason,
not by checking what number would look best against this app's own internal thresholds, and it is
comfortably longer than anything internal to this pipeline.

## 3. Number of shots

**Precommitted: 8 attempts.** Chosen now, not adjustable afterward. Reasoning: it sits in the
middle of your 7–10 range, and it comfortably clears this app's own already-documented session
-analytics minimums (≥4 shots for consistency stats, ≥2 makes and ≥2 misses for makes-vs-misses
comparison, ≥6 shots for trend splits — see `docs/METHODOLOGY.md`) with a small margin, without
extending the session long enough to risk fatigue-driven form drift partway through. **All 8
genuine attempts count, whatever happens.**

## 4. Ground truth

Fill this in by watching the raw recording once, start to finish, **before** ArcVision ever sees
it — no inference run first, no peeking at predictions.

```markdown
# arcvision_demo_02 — Ground Truth (recorded before inference)

Recorded: <date/time>
Video file: <exact filename>

| Shot # | Approx. release time (mm:ss) | Outcome (MADE / MISSED / AMBIGUOUS) | Notes |
|---|---|---|---|
| 1 |  |  |  |
| 2 |  |  |  |
| 3 |  |  |  |
| 4 |  |  |  |
| 5 |  |  |  |
| 6 |  |  |  |
| 7 |  |  |  |
| 8 |  |  |  |

Total genuine attempts: 8 (fixed in advance — see Section 3)
```

Use "AMBIGUOUS" honestly for any attempt that's genuinely unclear even to your own eye from this
camera angle — don't force a guess, and don't infer the label from what you expect ArcVision to say.

## 5. How ground truth will be frozen (before inference)

Matching the exact, already-proven precedent this project used for V4 (commit `fa9ee0d "Freeze
Video 4 ground truth before running inference"`):

1. Save the filled-in template as `docs/ARCVISION_DEMO_02_GROUND_TRUTH.md`.
2. `git add docs/ARCVISION_DEMO_02_GROUND_TRUTH.md`
3. `git commit -m "Freeze arcvision_demo_02 ground truth before running inference"`
4. Optionally, as an extra independent proof alongside the git commit:
   `Get-FileHash docs\ARCVISION_DEMO_02_GROUND_TRUTH.md -Algorithm SHA256` (PowerShell) and record
   the printed hash in the commit message or a note — this plus the commit timestamp is enough to
   prove the labels existed before any prediction was revealed.

Ground truth is not touched again after this point, regardless of what ArcVision outputs.

## 6. One-shot evaluation metrics

After ground truth is frozen, run the video once through the current frozen production pipeline
(no retries, no settings changes) and report:

- True shot count (8, per Section 3) vs. detected shot count.
- False positives: detected shot windows with no corresponding genuine attempt.
- False negatives: genuine attempts with no corresponding detected window.
- MADE/MISSED/UNKNOWN sequence, matched to ground truth by nearest release time.
- Confusion matrix (truth × prediction), same shape as the one already used for V4.
- Accuracy among classified (non-UNKNOWN) calls.
- UNKNOWN rate.
- Timing match: how closely each detected shot's release timestamp lines up with the logged
  approximate ground-truth time.

## 7. Precommitted public-demo decision rule

The new recording may replace the current public demo **only if all of the following are clearly
true** — this is a checklist, not a score to optimize, and it is not written to guarantee the new
video wins:

- All genuine shots are represented (no deceptive trimming of the video or the shot list).
- Low/no false-positive shot events.
- Substantially fewer UNKNOWN outcomes than the current demo (3/7 today).
- No increase in confident *incorrect* outcomes merely to gain coverage — a wrong confident call is
  worse than an honest UNKNOWN, not better.
- The replay is visually understandable to a viewer.
- The biomechanics/coaching output is genuinely useful (not degenerate/empty).

Perfect accuracy is explicitly **not** required. If the new recording does not clearly satisfy
this checklist, **stop** — do not adopt it, do not tune anything to help it pass, and do not
re-record for this reason. **Fallback: V1 remains the interactive example session**, and if it's
used, the documentation must describe it explicitly as *a real, precomputed example session, not
an independent generalization benchmark* — that role stays with V4 regardless of which video is
selected as the interactive demo.

## 8. No-cherry-picking rule (precommitted, applies regardless of outcome)

- Exactly **one** new recording attempt is evaluated under this protocol.
- No recording multiple sessions and picking the best-looking result.
- No deleting individual failed/UNKNOWN shots from the count or the video.
- No changing ground truth after inference is run, for any reason.
- No CV/threshold/detector/tracker/outcome/biomechanics/coaching changes based on this recording.
- No splicing favorable shots together from different takes.
- No re-running with different analysis settings looking for a better result.

**The one allowed exception**: the recording may be redone **only** for an obvious recording
failure discovered *before* inference is ever run — the camera fell or moved, the file is
corrupted, or the shooter/hoop was accidentally out of frame for a substantial portion of the
session. **Never** because ArcVision's output looked disappointing.

## 9. Tomorrow's exact command checklist (not run tonight — the video doesn't exist yet)

1. Record the video per Section 1.
2. Copy it into the repo root, e.g. `arcvision_demo_02.<ext>` (matching the existing
   `arcvision_demo_01.mov` naming convention). Then run
   `git check-ignore -v arcvision_demo_02.<ext>` — the existing `/*.mov` rule only matches a
   `.mov` extension; if the phone produces a different extension (e.g. `.mp4`), the root-level
   ignore rule will need a small, narrowly-scoped widening at that time (this is a repo-hygiene
   `.gitignore` edit, not a production/CV change) before the file is left sitting untracked-and
   -not-ignored.
3. Inspect metadata (duration, resolution, fps, codec, audio-stream presence) the same way
   `arcvision_demo_01.mov` was inspected — `ffmpeg -i <file>` via the already-available
   `imageio_ffmpeg` binary, or the `cv2.VideoCapture` snippet already used earlier this project.
4. If the recording contains audio you don't want public, create a muted copy **without
   re-encoding video**, exactly as before:
   `ffmpeg -i arcvision_demo_02.<ext> -c:v copy -an arcvision_demo_02_muted.<ext>`
5. Manually freeze ground truth per Section 4 (watch the raw video once, fill in the template,
   before any inference).
6. Hash/commit ground truth per Section 5.
7. Verify production code is unchanged: `git status`/`git diff` against `app/` should show nothing
   pending — confirm the pipeline being tested is genuinely the same frozen one, not something
   modified in between.
8. Run the production analysis **once**: start the real app (`.\run.ps1`), upload the (muted, if
   applicable) video through the actual `/api/sessions/upload` path — the same faithful, real
   production path already used for the current showcase video's own final rerun — and let it
   complete. No retries.
9. Generate the comparison per Section 6, against the frozen ground truth from Section 4.
10. Apply the decision rule in Section 7 and report the outcome — adopt, or stop and keep the
    current demo/V1 fallback, per whichever the checklist actually says.

Nothing here is executed tonight. No exporter, demo session, or production file was touched to
write this document.

---

## Summary

**A. Exact recording setup**: landscape, phone default resolution/fps (typically 1080p/30–60fps),
stationary camera, ~side/45° angle, ~20–30ft back, no digital zoom, full shooter body + hoop
continuously in frame, avoid strong backlighting, no other people, one continuous unedited take.

**B. Exact number of shots**: **8**, precommitted, all genuine attempts count.

**C. Shot pacing**: prepare → pause → shoot → let flight/rim interaction fully resolve → let the
result settle → retrieve → return → a clear, deliberate **2–3 second** stationary pause → next
shot. Not derived from any internal ArcVision timeout.

**D. Ground-truth template**: created above (Section 4), saved as
`docs/ARCVISION_DEMO_02_GROUND_TRUTH.md` when filled in tomorrow.

**E. How ground truth will be frozen**: filled in by hand from the raw video only, then
`git add` + `git commit` (matching the exact V4 precedent), with an optional SHA-256 hash as
extra proof — all before inference is ever run.

**F. One-shot evaluation metrics**: shot-count match, false positives/negatives, outcome sequence
and confusion matrix vs. ground truth, accuracy among classified, UNKNOWN rate, timing match.

**G. Precommitted demo acceptance rule**: all of — full representation, no trimming, low/no false
positives, substantially fewer UNKNOWNs than today's 3/7, no new confident-wrong calls, an
understandable replay, useful coaching output. Not a guaranteed win; perfect accuracy not required.

**H. V1 fallback rule**: if the new recording doesn't clearly clear G, keep V1 as the interactive
example session, explicitly documented as a real precomputed example, not a generalization
benchmark — that role stays with V4 either way.

**I. Recording-failure exception**: redo only for camera movement/fall, file corruption, or
substantial shooter/hoop framing loss discovered *before* inference — never for a disappointing
ArcVision result.

**J. Tomorrow's exact sequence**: the 10 steps in Section 9, in order, no step skipped or reordered.

**K. Confirmation**: no production file was modified to produce this document. This session made
exactly one change: creating `docs/FINAL_DEMO_RECORDING_PROTOCOL.md`. No inference was run, no
video was recorded or copied, no exporter or demo session was touched, nothing was staged or
committed.
