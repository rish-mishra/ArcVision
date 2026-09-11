# ArcVision — Methodology

This document explains exactly what every number in the dashboard means, what it is computed
from, and what its limitations are. If a metric isn't listed here, it isn't shown to the user.

## Coordinate systems — read this first

Every measurement in ArcVision is one of three kinds, and the UI never presents one as another:

1. **Image-space** — raw pixel positions/sizes in the *analysis-resolution* frame (video is
   downscaled to a max dimension of 960px and resampled to ~30fps before analysis for speed;
   see `app/config.py::VideoConfig`). Used internally for tracking and geometry, rarely shown
   directly.
2. **Body-relative (normalized)** — a distance expressed as a fraction of the shooter's own
   torso length (shoulder-midpoint to hip-midpoint) in that frame. This cancels out how close
   the camera is or how zoomed the shot is, which is what makes it usable for *comparing this
   player's own shots to each other*. It is **not** a physical unit (not centimeters, not
   inches) and is never presented as one.
3. **Calibrated physical units** (meters, m/s, real launch angle) — **not implemented in V1**.
   Producing these honestly requires known real-world reference geometry (e.g. a calibrated
   rim height/diameter and a camera pose solve), which V1's classical-CV hoop detector does not
   yet provide with enough reliability. Rather than fabricate a "launch angle: 47°" or
   "release velocity: 6.2 m/s" from an uncalibrated monocular camera, ArcVision omits these
   entirely. Joint **angles** (elbow, knee, torso lean) are the exception: an angle between three
   points is scale-invariant, so it's valid without calibration.

## Detection & tracking pipeline

| Stage | Approach | Why |
|---|---|---|
| Person detection | YOLOv8n (COCO-pretrained), class "person" | Fast, GPU-accelerated, reliable at typical gym/court distances. The largest, most temporally-consistent person box is treated as the primary shooter (`app/vision/detection/person_selector.py`). |
| Pose estimation | MediaPipe BlazePose (`model_complexity=1`), run on the shooter's crop | Well-validated, real-time-capable, Apache-2.0 licensed, 33 landmarks (we use 13: nose, shoulders, elbows, wrists, hips, knees, ankles). |
| Basketball detection | TWO candidate sources, pooled: (1) YOLOv8n COCO class "sports ball" + color/circularity validation (`app/vision/detection/ball_detector.py`), (2) YOLO-World open-vocabulary detection prompted directly as "basketball" (`ball_detector_learned.py`) | COCO has **no basketball-specific class**, and on a real test video its "sports ball" class recalled a held/occluded basketball in under 10% of frames even at increased inference resolution. The same frames prompted through YOLO-World as "basketball" recalled ~37% instead -- still imperfect (a small, fast, sometimes motion-blurred ball near a backboard/rim remains a hard case for both), which is exactly what the Kalman tracker's gap-bridging and the shot state machine's fallback trigger below exist to absorb. |
| Ball tracking | Custom constant-velocity Kalman filter (`app/tracking/kalman_tracker.py`) | Bridges short detector gaps (occlusion by the shooter's hand, motion blur) for up to `TrackerConfig.max_extrapolation_frames` frames, clearly labeling each point `detected` / `interpolated` / `predicted` / `unavailable`. Long gaps are reported as unavailable, never silently guessed. |
| Hoop detection | TWO candidate sources, pooled: (1) classical CV -- orange-color mask + contour/Hough-circle candidates (`hoop_detector.py`), (2) YOLO-World open-vocabulary detection prompted as "basketball hoop/rim/backboard/net" (`hoop_detector_learned.py`) -- aggregated across a sample of frames | A real test video's rim was dark/weathered metal against a bright overcast sky, which produced zero color-mask pixels for the entire session -- the classical detector's orange-rim assumption doesn't hold universally. YOLO-World has no color assumption and consistently (if not confidently, per-frame) located that rim instead. Pulling a random community-trained rim-detection model was avoided for license-provenance and offline-availability reasons; YOLO-World's weights come from Ultralytics' own trusted release channel, the same one `yolov8n.pt` already uses. Because the camera is assumed near-stationary for the session, a location consistently proposed across many DISTINCT frames is trusted; a one-off detection, or several near-duplicate detections within the same one or two frames, is not (see `app/tracking/hoop_aggregator.py`'s per-frame deduplication). |

## Detector architecture (basketball-specific RF-DETR)

The generic detector stack above (YOLOv8n COCO classes + YOLO-World open-vocabulary prompts)
was the V1 approach because COCO has no basketball/rim classes at all. On real footage it
worked but left a real, measured gap exactly where outcome detection needs evidence most: the
ball's immediate vicinity around the rim. A second phase of work replaced it with a
basketball-specific detector, fine-tuned rather than prompted, while keeping the generic stack
in the codebase as an automatic fallback.

### Model

[RF-DETR-Small](https://github.com/roboflow/rf-detr) (Roboflow, Apache-2.0, `pip install
rfdetr`), fine-tuned from its COCO-pretrained checkpoint on a basketball/rim dataset (below).
Small (32.1M params, 512×512 input) was chosen over Nano/Medium/Large by measuring actual
headroom on this machine's GPU (RTX 4050, 6GB VRAM): the COCO-pretrained Small model used well
under 200MB for single-image inference, leaving ample room without needing Nano's resolution
cut or Medium/Large's extra cost. One forward pass yields both classes (`ball`, `rim`) at once,
replacing four separate detector calls (YOLOv8 person+ball, YOLO-World ball, classical hoop,
YOLO-World hoop) with one -- see `app/vision/detection/ball_rim_detector_rfdetr.py`.

### Dataset

[University of Arizona "Basketball Shooting Robot"](https://universe.roboflow.com/the-university-of-arizona-th1yv/basketball-shooting-robot)
(Roboflow Universe), **CC BY 4.0** (commercial use and derivative training permitted with
attribution -- credited here). A real complication surfaced during acquisition: the dataset's
one *generated, downloadable* version contains **only the `rim` class** (verified: its 10,140
rim annotations match the raw project's rim total exactly, with zero ball/basketball
annotations at all) -- whoever generated that version excluded the ball classes. Rather than
substitute a different, less appropriate dataset, `scripts/fetch_ball_rim_annotations.py`
pulls `ball`/`basketball`/`rim` annotations directly from the raw project via Roboflow's
per-image search/detail API (read-only; never attempted to write a new version to a project we
don't own), downloading each image's original file and full bounding-box geometry. 9,612
images, 17,258 boxes after `scripts/prepare_ball_rim_dataset.py` merges the overlapping
`ball`+`basketball` source labels into one `BALL` class and keeps `rim` as `RIM` (no
`backboard` class exists anywhere in this source project; `person`/`people`/`made`/`shoot`
labels were never fetched at all). Splits reuse the source project's own train/valid/test
assignment (7,845 / 1,126 / 641 images) rather than re-splitting.

### Training

`scripts/train_ball_rim_detector.py`: RFDETRSmall, `batch_size=2, grad_accum_steps=8` (a 6GB
laptop GPU's conservative version of RF-DETR's effective-batch-16 guidance), `lr=1e-4`,
`epochs=40` with early stopping (`patience=8`) -- stopped at epoch 9 once validation metrics
plateaued (~18.5 min/epoch on this hardware). Two Windows-specific infrastructure issues had to
be solved, not worked around by disabling anything security-relevant:

- **Windows Smart App Control** blocked `faster_coco_eval`'s compiled evaluation extension
  (confirmed via Windows Event Log Code Integrity events: "did not meet the Enterprise signing
  level requirements") -- RF-DETR's training pipeline imports it unconditionally just to build
  an evaluator class that's dead code for a plain bbox model, since the actual mAP computation
  goes through `torchmetrics.detection.MeanAveragePrecision`, which natively supports (and
  defaults to) a `backend="pycocotools"` mode needing no such extension. A no-op stand-in
  module (`.venv/Lib/site-packages/sitecustomize.py`, auto-imported by every Python process
  using this venv -- necessary because PyTorch DataLoader workers spawn fresh interpreters on
  Windows, so a same-process patch alone doesn't reach them) satisfies the import, and
  `scripts/_rfdetr_compat.py` redirects the actual evaluation backend to the verified-working
  `pycocotools` path. No system security setting was changed.
- A Windows console Unicode crash in RF-DETR's `rich`-based metrics-table rendering was fixed
  by forcing `PYTHONIOENCODING=utf-8`/`PYTHONUTF8=1`.

**Validation metrics** (epoch 9, best checkpoint): mAP50 ≈0.97, ball F1 ≈0.94 (precision
≈0.93, recall ≈0.95), rim F1 ≈0.98 (precision ≈0.98, recall ≈0.97). Full config, dataset
metadata, and exact dependency versions are saved alongside the checkpoint in
`data/training_runs/rfdetr_ball_rim_v1/`.

**Class-index note for anyone touching the adapter**: RF-DETR re-indexes categories to a
0-based internal list regardless of the COCO category `id` values used to prepare the dataset
(this project's prep script used id=1 for ball, id=2 for rim, COCO convention) -- the trained
checkpoint's own `class_names` attribute and actual `.predict()` output confirmed class_id 0 =
ball, 1 = rim. `CLASS_ID_TO_NAME` in `ball_rim_detector_rfdetr.py` documents this explicitly;
re-verify against a real checkpoint before ever changing it.

### A/B benchmark (independent of the training run's own validation metrics)

`scripts/benchmark_ball_rim_detectors.py` ran both stacks over every one of 1,514 analyzed
frames of the real test video, independent of the Kalman tracker/outcome detector (raw
per-frame detection quality, not what a smoothing layer does with it). Full report:
`data/diagnostics/detector_benchmark/benchmark_report.json`.

| Metric | Existing stack | RF-DETR |
|---|---|---|
| Ball: overall frame coverage | 23.0% | 80.8% |
| Ball: near-rim coverage (last 30% of each shot's flight) | ~0% for 6/7 shots | 88-100% for 6/7 shots (64.7% worst case) |
| Ball: mean detection confidence | 0.314 | 0.693 |
| Ball: longest in-flight blackout | up to 51 frames | 1-3 frames |
| Rim: frame coverage | 71.3% | 99.4% |
| Rim: aggregated confidence | 0.607 | 0.963 |
| Rim: positional stability (std px) | 9.39 | 1.42 (~6.6× tighter) |
| Processing speed | 28.0 fps (4 model calls/frame) | 38.9 fps (1 model call/frame) |

Every axis improved, including speed, despite RF-DETR being the more thorough detector.

### Visual benchmark

`scripts/visual_benchmark_frames.py` produced side-by-side annotated comparisons
(`data/diagnostics/detector_benchmark/visual/`) on the specific hard cases outcome detection
depends on: hand-occluded ball, just-released ball, small ball against bright sky, ball
approaching/overlapping the rim, ball inside the net, ball falling below the rim, and an idle
frame (false-positive check). RF-DETR correctly detected the ball in 7 of 8 cases (missing
only the deliberately ball-free idle frame -- correctly, no false positive); the existing stack
detected it in 2 of 8, missing every near-rim case including one where the ball is clearly
visible inside the net. The existing stack's rim/hoop candidates in several of these frames
were near-zero-confidence noise (0.01-0.04) that happened to land on the ball or elsewhere, not
the rim.

### Production integration

Given the results above, RF-DETR is now the **primary** ball/rim source in
`app/pipeline/orchestrator.py` (`BallRimDetectorConfig` in `app/config.py`). The older
detectors were **not deleted**:

- If the checkpoint (`models/rfdetr_ball_rim_v1.pth`) is missing or `ball_rim_rfdetr.enabled`
  is set `False`, the pipeline automatically falls back to the full YOLOv8/YOLO-World/
  classical-CV stack, with an explicit warning surfaced in session results -- the app still
  works on a fresh checkout before anyone runs training.
- They remain the standalone diagnostic/comparison tooling this whole benchmark was built with
  (`scripts/benchmark_ball_rim_detectors.py`, `scripts/visual_benchmark_frames.py`).

One existing heuristic became genuinely obsolete rather than merely redundant: the near-hoop
enrichment pass (`app/vision/detection/near_hoop_enrichment.py`, a multi-frame chain-builder
designed specifically to recover ball evidence the *global* detector missed near the rim) is
now skipped whenever RF-DETR is active, since RF-DETR already closes that exact gap directly
(the benchmark's near-rim coverage numbers above). It stays in the codebase, still exercised by
its own tests, and still runs automatically in the fallback path.

### A downstream discovery: denser ball data exposed a real shot-segmentation bug

Re-running the full pipeline on the real video initially produced 8 shots instead of the
validated 7 -- investigating (not tuning around it) found a genuine, previously-latent bug in
`_genuine_knee_dip_nearby` (`app/events/shot_state_machine.py`): it checked only the RANGE
(max − min) of knee angle in a lookback window, with no regard for temporal direction. The
video's very first frames caught the shooter already mid-motion, knees bent from whatever
happened just before the clip starts, simply straightening to a normal stance as they picked up
the ball -- a `max − min` well over the 12° threshold, but running backwards (extending, never
bending), not a real shooting load. This was invisible under the old, sparser detector stack
(the primary/fallback triggers rarely even reached this check with clean enough data to expose
it) and became reachable once RF-DETR's much denser, more confident ball tracking made the
triggers fire more reliably. The fix requires the window's minimum to have a genuinely higher,
extended value strictly BEFORE it (confirming a real bend from a standing baseline) -- and
deliberately does NOT also require a rise after the minimum, since the same function is called
live, evaluating the current frame as the fallback trigger watches an upward burst unfold, where
the deepest bend legitimately coincides with the frame being evaluated (an initial "require both
sides" fix reverted the real release frame back to `idle` instead of progressing to
`upward`/`flight` -- confirming that requirement was wrong, not just cautious, and cutting the
shot count to 6). Regression test: `test_knee_only_straightening_at_clip_start_is_not_a_genuine_load`
in `tests/test_shot_state_machine.py`. Final, re-verified result: 7 shots, matching the
previously validated count, with all seven release timestamps close to (within ~1s of) the
original detector stack's.

### Pose model comparison (MediaPipe retained)

`scripts/compare_pose_models.py` compared MediaPipe BlazePose (current) against RF-DETR
Keypoint (`RFDETRKeypointPreview`, zero-shot COCO-17, no training needed) on all seven real
release frames. Finding: MediaPipe's own confidence is consistently much lower on this
shooter's right elbow/wrist during release (0.24-0.44) than RF-DETR's (0.70-0.99) on the same
joints -- but RF-DETR Keypoint is ~4-8× slower even on GPU (only ships as an "xlarge" model),
and the two disagree on position by 14-125px with no ground truth available to say which is
right. **MediaPipe was retained** as the primary pose estimator -- the practical case for a
wholesale replacement wasn't there -- but this is flagged as a concrete, scoped candidate for
future work: a corroborating RF-DETR Keypoint check specifically at each shot's release frame
(cheap -- one extra frame per shot, not the whole video) rather than a full swap.

### Retraining / replacing the model

1. `scripts/download_basketball_dataset.py` (needs a Roboflow API key in `.env`, never
   printed/logged) or point `scripts/prepare_ball_rim_dataset.py` at a differently-sourced
   COCO-format dataset with `ball`/`rim` classes.
2. `scripts/fetch_ball_rim_annotations.py` if pulling from the raw project again (resumable --
   safe to re-run after an interruption).
3. `scripts/prepare_ball_rim_dataset.py` to remap classes and assemble the final COCO dataset.
4. `scripts/train_ball_rim_detector.py` (edit `EPOCHS`/`BATCH_SIZE`/`GRAD_ACCUM_STEPS` at the
   top for different hardware).
5. Copy the resulting `checkpoint_best_ema.pth` to `models/<new_name>.pth` and update
   `BallRimDetectorConfig.checkpoint_name` in `app/config.py`.
6. Re-run `scripts/benchmark_ball_rim_detectors.py` and `scripts/visual_benchmark_frames.py`
   before trusting a new checkpoint in production -- don't skip the A/B step.

## Shot segmentation (state machine)

A shot attempt is recognized by a finite-state sequence, **not** by "ball moved upward" alone
(`app/events/shot_state_machine.py`):

`IDLE → LOAD → UPWARD → RELEASED → FLIGHT → (reset) → IDLE`

- **LOAD**: the ball is near the shooting hand (within a torso-length-normalized distance
  threshold) and knee angle is being tracked.
- **UPWARD**: a strong upward ball velocity is observed while still near the hand — this is
  what distinguishes a real shot's release burst from a dribble (small, sub-threshold vertical
  oscillation) or a pass (lateral motion without a comparable upward burst).
- **RELEASED → FLIGHT**: the ball has sustained separation from the hand for multiple
  consecutive frames (guards against one noisy frame triggering a false release).
- **Reset**: a shot only closes out, and a new one can only begin, after the ball is
  *confirmed* back near the body for several consecutive frames. The ball simply going
  undetected is explicitly NOT treated as evidence of retrieval (a real test video's ball
  detection dropped out for stretches during genuine flight; treating that absence as
  "retrieved" closed every shot window before the ball had traveled anywhere near the hoop).
  An unresolved, total tracking blackout still closes the window eventually, on a separate,
  more patient budget sized to how long a real shot's flight can physically take -- otherwise
  a lost ball could run one shot's window into the start of the next.

**Fallback trigger.** The LOAD phase above requires the ball to be directly tracked near the
shooting hand. On real footage this can fail often -- a held/gripped ball is smaller and more
occluded than one in open flight, which is exactly what dragged basketball-detection recall
down (see the detection table above). If continuous ball-hand tracking were required to ever
start a shot, a session with that detection profile would report zero shots despite every
release being directly observable in the data. So the machine also recognizes a sustained,
confirmed upward ball flight (rising above shoulder height) as a release-in-progress on its
own, even with no directly-observed LOAD phase, and reconstructs the load window afterward from
the pose-only knee-angle trace in the seconds before it -- pose tracking is markedly more
reliable than ball tracking in practice. Shots detected this way carry an explicit
`load_phase_inferred_from_pose_only_ball_not_tracked_near_hand` warning.

**Coherent-evidence requirements (second real-video calibration pass).** Testing the fallback
trigger against a full real session (9 detections against 7 known genuine shots) found two
false positives, both sharing the same root cause: "ball near/away from hand, then moving up
fast" is not, by itself, a shot signature -- a **rim rebound** (ball bounces back upward past
shoulder height while the shooter stands still watching it) and a **dribble while walking** (a
bounce produces the same brief upward-velocity spike) both satisfied it. Both also happened to
produce a measurable knee-angle swing large enough to look like a load at first pass -- a
rebound's swing turned out to be borrowed from the *previous* shot's own genuine load sitting
in the same lookback window, and the dribble's was real, ordinary gait flexion, not noise. Shot
segmentation now requires **all** of the following before either trigger path confirms a
release, each skipped (not blocking) when its underlying data is unavailable:

1. A genuine knee-flexion dip (`ShotDetectionConfig.load_knee_flexion_drop_deg`) somewhere in
   the recent history leading up to the burst -- checked by looking backward from wherever the
   burst is, not just forward from wherever ball-tracking happened to confirm hand proximity
   (which, per the point above, is frequently late).
2. That lookback window never reaches into, or before, the **previous** shot's own window --
   otherwise a real earlier load can be misattributed to an unrelated later burst (the rebound
   failure mode).
3. The shooter's hip position stayed within a few torso-lengths
   (`max_load_hip_translation_norm`) over that same window -- a jump shot is taken from an
   essentially stationary base, while gross horizontal translation (walking) is not, which is
   what actually separates a real load from ordinary gait flexion (the dribble failure mode).
4. For the fallback trigger specifically, at least one frame in the qualifying burst must be a
   genuinely **observed** ball position (`DETECTED`/`INTERPOLATED`), not purely a Kalman
   extrapolation (`PREDICTED`) -- the tracker's own momentum guess is not, on its own, evidence
   of a real release.

Knee-angle readings themselves are also sanity-checked against a biomechanical plausibility
floor (`PoseConfig.min_plausible_knee_angle_deg`) before being used at all: a real session
produced isolated ~50-80° readings during a moment two people's poses overlapped in frame,
almost certainly pose-estimation noise rather than an actual near-ground squat, and noise of
that scale is large enough to otherwise pass the flexion-drop check on its own.

## Release detection

The state machine's separation-based candidate frame is refined (`app/events/release_detector.py`)
by checking, in a small window around it: (1) hand-ball distance crossing a tighter threshold,
(2) sustained upward ball velocity, and (3) shooting-elbow extension ≥140°. Each corroborating
signal raises confidence; when none refine the estimate, the state machine's original candidate
is kept with lower confidence, and the release is reported with an explicit confidence score
plus a small bounded uncertainty window rather than a falsely precise single frame.

## Make / miss / unknown

Outcome detection (`app/events/outcome_detector.py`) reasons about the ball trajectory as an
explicit sequence of phases -- RELEASE → ASCENT → APEX → DESCENT → HOOP APPROACH → RIM
INTERACTION → POST-RIM MOTION -- rather than checking isolated coordinates. This is a full
redesign after an earlier version let every shot on a real test video resolve to the same
generic "ball later far from hoop" branch with an identical confidence score, which turned out
to be satisfiable by an ordinary post-catch ball position rather than genuine rim-interaction
evidence.

**Preprocessing.** Before any phase reasoning, the trajectory is (1) filtered to reliable points
only (`DETECTED`/`INTERPOLATED` -- never `PREDICTED`-only, i.e. never a purely Kalman-extrapolated
guess with no real detection behind it), then (2) passed through an outlier filter that drops
INTERPOLATED points sitting far from the straight line between the nearest genuine DETECTED points
bracketing them. This was added after diagnosing a real trajectory that contained a physically
impossible single-frame reversal -- the ball tracker briefly locked onto a different candidate
(most likely background clutter) before recovering -- which would otherwise have been read as
real ball motion.

A DETECTED point is **never** rejected here, and the anchor for "what's the expected position"
is always the nearest bracketing DETECTED points (searching outward through the whole sequence),
not raw immediate list-neighbors. This was a second, later real-video finding: the first version
checked every point (detected or interpolated alike) only against its immediate neighbors, which
meant a run of several INTERPOLATED points that were mutually self-consistent -- a stale Kalman
bridge from a bad association, not the real ball -- could locally outnumber and outvote the
genuine, isolated DETECTED points around it, causing the filter to discard the real evidence and
keep the fabricated cluster. Concretely, this caused a confident but false MISSED call on a shot
that was actually MADE: two high-confidence DETECTED points showing the ball converging on the
hoop were thrown out because they disagreed with a self-consistent-but-wrong interpolated run,
which both corrupted the apex estimate and left only far-from-hoop points to reason from. Since
an INTERPOLATED point is by construction just the tracker's own guess extending from its last
match, it should never be trusted enough to overrule an actual detection.

**Apex and phases.** The apex is the reliable point with the smallest image-y (highest position).
If the apex sits at either end of the observed trajectory (meaning the true peak may never have
been seen -- the track could still be rising when it ends, or already falling when it begins),
the detector requires substantially more total points before trusting the ascent/descent split at
all. Points at/after the apex are the descent phase; rim interaction can only be reasoned about
from descent points, since a real approach-to-hoop is definitionally part of the descent.

**MADE** requires a chronologically-ordered above-rim → below-rim crossing within a *tight*
horizontal band around the rim (sized from both the rim's own radius and the ball's own observed
radius, so apparent-size/perspective variation is accounted for), within a bounded frame gap, with
nothing observed *between* those two points that shows the ball leaving even a wider zone (which
would indicate a bounce rather than a clean pass-through). A single frame of bounding-box overlap
is explicitly never sufficient.

**MISSED** requires one of three positive evidence patterns, never merely "no make was found":
(1) the ball is observed entering a wider near-hoop zone from above, then a later reliable point
shows it clearly deflected back out of that zone (a rim/backboard rejection); (2) the ball is
observed at rim height but clearly outside even the wide zone, with points confirming it came
from above (passed beside the hoop entirely); or (3) the ball's descent is confidently observed
well clear of the hoop the whole time, with real height context establishing it came from above
first (a clear airball). Post-shot catches, the ball simply appearing far away later, or the
track ending are explicitly **not**, by themselves, any of these three patterns.

**UNKNOWN** is the default whenever none of the above is met -- a first-class outcome, not a
fallback to minimize. Common causes: too few reliable points anywhere, an unconfirmed apex, the
descent phase itself having too few points (the hoop-approach and rim-interaction phases both
live in the descent, so an ascent-heavy trajectory that goes dark right after the peak cannot
support a call either way), or a hoop location that isn't confident enough to trust at all.

Every outcome carries a numeric confidence (built from corroborating-point counts, crossing-gap
size, source reliability, track-identity stability, and hoop confidence -- never a fixed
constant) and a structured `evidence` dict (apex frame, ascent/descent point counts, band sizes,
outlier count, track stability, the specific frames involved) alongside the plain-text reason, so
a finding can be checked against the source video rather than taken on faith. Track-identity
stability (`n_detected / n_reliable` after outlier rejection) discounts confidence for a
trajectory that leans heavily on interpolation over genuine detection, since such a track is more
exposed to bad-association bridging than one built mostly from real detections, even when both
show the same phase evidence.

### Near-hoop ball detection

The global ball tracker (see the detection table above) is built once for the whole video, before
the hoop's location is even known, and on a real test video its trajectory never reached within
300px of a 39px-radius rim for any of seven real shots -- exactly the evidence outcome detection
needs most. A second pass (`app/vision/detection/near_hoop_enrichment.py`) re-reads each shot's
flight window specifically, crops a region around the (now-known, static) hoop, upscales it, and
re-runs detection there -- the same principle that made prompting a detector directly as
"basketball" pay off elsewhere in this pipeline: a small object occupies far more of the frame
once cropped and enlarged.

A single-frame confidence floor was tried first and found insufficient: in this footage's bright,
overcast lighting, the open-vocabulary learned detector found nothing at all in the hoop's
vicinity, and the classical (color/circularity) fallback caps every single-frame candidate at a
flat, low score because only one of its two corroborating cues (shape, color) passes at a time
against an overexposed sky. No fixed threshold can separate a genuine ball sighting from clutter
(net wires, backboard edges, fixed background features) when the discriminating signal was never
in any one frame's score to begin with.

What the current design uses instead is temporal coherence: for each shot, a single chain is
built starting from the shot's own last genuine (DETECTED/INTERPOLATED) point, extended frame by
frame to whichever ROI candidate is closest to the position **predicted from the chain's own
observed velocity** (not a frozen last-known position, which would otherwise let the acceptance
radius balloon over a long gap until it accepts whatever's nearby). The gate itself is calibrated
from this same video's own observed ball speed (the 95th percentile of consecutive genuine
DETECTED displacements), never a hardcoded constant. A candidate that repeats the same pixel
position for more than a couple of consecutive frames ends the chain right there, since a ball in
flight essentially never holds one exact position -- that pattern is far more consistent with the
detector having locked onto a fixed background feature. A final pass fits the accepted chain to
simple projectile motion (constant horizontal velocity, constant vertical acceleration -- a
reasonable model over one shot's brief flight, not a claim of full 3D calibration) and iteratively
drops whichever point disagrees with that fit the most. Only a chain that reaches a minimum length
is trusted at all; a shorter one is discarded in full rather than partially trusted.

This is a genuine improvement over flat single-frame thresholding -- it recovered real,
defensible near-hoop evidence for shots that previously had none -- but it is not fully robust on
this footage: different reasonable choices for the pruning threshold were observed to change the
outcome for multiple shots, not just the one under investigation, which indicates the underlying
per-frame candidates are noisy enough that no downstream chain-repair heuristic fully closes the
gap. Where the chain doesn't reach a confident, stable conclusion, the outcome detector correctly
falls back to UNKNOWN rather than a forced call. This enrichment only ever *adds* points where the
global trajectory had nothing (`UNAVAILABLE`) or a bare Kalman guess (`PREDICTED`) -- it never
overrides an existing real detection, and it is entirely separate from the trajectory shot
segmentation and biomechanics use, so it cannot affect those.

## Biomechanics metrics (`app/biomechanics/metrics.py`)

All angles use the standard three-point formula (angle at the middle point, e.g. hip-knee-ankle
for knee flexion; shoulder-elbow-wrist for elbow extension), computed from MediaPipe landmarks
in normalized image coordinates — valid regardless of camera distance.

| Metric | Definition | Space |
|---|---|---|
| Knee angle at load | Angle at the shooting-side knee (or the average of both legs if shooting side is undetermined) at the frame of deepest flexion between load-start and release | degrees |
| Knee angle at release | Same joint angle at the release frame | degrees |
| Elbow angle at load / release | Angle at the shooting-side elbow at the same two frames | degrees |
| Torso lean at load / release | Angle of the hip-midpoint→shoulder-midpoint line from vertical | degrees |
| Release height | (hip-midpoint y − wrist y) at release, divided by torso length | body-lengths above the hip |
| Release horizontal offset | (wrist x − shoulder-midpoint x) at release, divided by torso length | body-lengths |
| Load / upward / total prep duration | Wall-clock time between the corresponding state-machine phase boundaries | seconds |
| Trajectory straightness | Straight-line displacement ÷ total path length of reliable ball points during flight | ratio, 1.0 = perfectly straight |
| Trajectory apex height | (release-point y − minimum y observed during flight) ÷ torso length at release | body-lengths |

Every metric that cannot be computed (missing/low-visibility landmarks, no release detected,
insufficient reliable ball points) is returned as `null`/absent with the specific reason logged
in that shot's `warnings`, never estimated.

## Physical-unit calibration (`app/biomechanics/rim_calibration.py`)

Everything above is body-relative or angular by design (see "Coordinate systems"). A regulation
basketball rim's inner diameter -- 18 inches / 0.4572m -- is the one genuinely known real-world
size anywhere in this pipeline, so it's tempting to use it to convert pixel measurements to
physical units generally. That temptation is exactly what this module refuses to do beyond one
narrow case, and the reasoning matters: a single object's known size gives a pixels-per-meter
ratio that is valid ONLY at that object's own distance from the camera. Applying it anywhere
else in the frame silently mixes in whatever perspective foreshortening exists between the two
depths -- which a single, uncalibrated camera has no way to measure or correct for.

- **MEASURED**: nothing. There is no ground-truth-verified physical measurement anywhere in
  this pipeline.
- **ESTIMATED** (rough, single-reference, valid only at the rim's own depth): ball speed between
  two genuinely `DETECTED` (never interpolated/predicted) points that are both within the rim's
  near-vicinity, surfaced as `rim_entry_speed_mps_estimate` in a MADE shot's `outcome_evidence`
  when defensible (`app/events/outcome_detector.py`'s crossing-pair evidence). This is
  deliberately the only physical-unit number this pipeline reports anywhere, and it is not
  displayed with false confidence -- absent when the calibration wouldn't be valid, never a
  guess.
- **NOT RELIABLY RECOVERABLE**: release velocity, release height, general shot speed, full shot
  arc height, entry angle. Every one of these either occurs entirely at the shooter's depth
  (which the rim's calibration is NOT valid for) or spans multiple depths as the ball travels
  from shooter to rim (where the true scale changes continuously and unpredictably without a
  second reference point). Adding these would require actual camera calibration -- e.g. two
  known-size references at different depths, or a calibration pass with a checkerboard -- not
  more clever pixel math on top of one reference. They are intentionally absent rather than
  approximated.

## Shooting side

Determined per-shot by comparing mean wrist-to-ball distance for the left vs. right wrist
across the shot's load+upward window (`app/biomechanics/shooting_side.py`); whichever wrist
stays closer to the ball is the shooting hand. If neither wrist has a reliable ball-proximity
signal, shooting side is reported as undetermined and side-specific metrics fall back to a
two-leg average where defensible (knee angle) or are omitted (elbow angle, which has no
meaningful non-side-specific fallback).

## Session analytics

- **Consistency** (`app/analytics/consistency.py`): coefficient of variation (std. dev. ÷ mean)
  per metric across all valid shots in the session. Requires at least 4 valid samples for a
  given metric; otherwise reported as insufficient rather than a misleading number from 1–2 shots.
- **Makes vs. misses** (`app/analytics/makes_vs_misses.py`): for each metric, compares the
  made-shot group to the missed-shot group using the mean, standard deviation, Cohen's *d*
  effect size, and (as an additional descriptive signal, not a claim of statistical proof)
  a Welch's t-test p-value. Requires ≥4 total classified shots and ≥2 makes and ≥2 misses;
  below that, the whole comparison is skipped with an explicit reason rather than reporting a
  shaky finding from a handful of shots. Unknown-outcome shots are excluded from this
  comparison entirely.
- **Trends** (`app/analytics/trends.py`): splits the session into first/last thirds *by shot
  order* (not clock time) and compares each metric's mean, plus shooting percentage. Requires
  ≥6 total shots. Never labeled as physiological "fatigue" — only as an observed change in
  measured mechanics/outcome across the session.
- **Feedback** (`app/analytics/feedback.py`): surfaces the 1–3 largest-effect-size, adequately
  sampled differentiators from the makes-vs-misses comparison, plus any notable session trend.
  If nothing clears the sampling/effect-size bar, the dashboard says so explicitly
  ("No strong measurable difference was found") instead of inventing a tip.

## Confidence handling

Every shot record carries independent confidence/quality scores for pose, ball tracking, hoop
location, release detection, and outcome classification. A shot can be included in the
shot-by-shot review while still being **excluded from session analytics** (e.g. release could
not be estimated at all) — this is tracked explicitly via `excluded_from_analysis` /
`exclusion_reason` so one bad detection cannot silently corrupt session-level statistics.

## Known limitations (V1)

- Single shooter, single ball, single hoop, mostly-stationary camera. Not validated for full
  game footage, multiple simultaneous shooters, or heavy camera motion/panning.
- **Basketball/rim detection near the hoop was the primary weakness in V1 and has since been
  substantially closed** by the fine-tuned RF-DETR detector (see "Detector architecture" above)
  -- benchmarked near-rim ball coverage went from ~0% to ~90%+ of frames on the real test video,
  and rim positional stability improved ~6.6×. This is now the PRIMARY detector; the older
  COCO+YOLO-World+classical-CV stack and its near-hoop chain-building enrichment pass remain in
  the codebase as an automatic fallback (only used if the RF-DETR checkpoint is missing or
  explicitly disabled) and as standalone diagnostic/comparison tooling. The fallback path's
  known limitations (near-hoop recall as low as ~0% on some real footage, projectile-fit
  pruning sensitivity) still apply if the app is ever run without the fine-tuned checkpoint --
  see the fallback-specific notes still in `app/vision/detection/near_hoop_enrichment.py` and
  `hoop_roi_ball_detector.py`.
- RF-DETR was fine-tuned on one dataset (University of Arizona, mostly outdoor courts). It has
  not been validated against indoor gym lighting, a significantly different rim/net/backboard
  design, or a camera angle very different from the training distribution -- the honest claim is
  "substantially better on the real footage this was benchmarked against," not "solved for all
  basketball footage." Re-running the A/B benchmark scripts against new footage before trusting
  results on a materially different setup is recommended.
- Hoop detection (in the fallback path) can still fail on a rim that's extremely small/distant
  in frame, or in scenes with no rim-hoop-like structure a learned detector can recognize at
  all. When this happens, mechanics are still analyzed but makes/misses are reported as
  unavailable for the session.
- Physical (metric) measurements are extremely limited by design -- one rough, rim-depth-only
  ball-speed estimate near a MADE crossing, nothing else (see "Physical-unit calibration"
  above). Everything else physical is body-relative or angular (see "Coordinate systems").
- Statistics on small samples (a typical session) are descriptive, not inferential proof;
  minimum sample-size gates exist specifically to avoid overstating what a handful of shots can
  actually tell you.
- The outcome detector's trajectory-outlier filter is a local straight-line consistency check
  anchored to genuine detections, not a full physics fit -- it catches gross, single-frame
  tracking-hijack artifacts and multi-frame fabricated interpolation runs (both confirmed on real
  footage) but would not catch a subtler drift where the detector itself repeatedly, confidently
  locks onto the wrong object across several consecutive frames.
- MediaPipe remains the primary pose estimator after a direct comparison against RF-DETR
  Keypoint found no clear practical win (see "Pose model comparison" above) -- but MediaPipe's
  own confidence is measurably, consistently lower on this shooter's release-side elbow/wrist
  than RF-DETR Keypoint's, a real, unresolved gap worth a future targeted (not wholesale) fix.
