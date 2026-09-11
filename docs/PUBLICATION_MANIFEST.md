# ArcVision — Publication Manifest

An explicit, allowlist-style publication plan. **No `git add -A`, ever** — this
document exists specifically so staging can be done by category instead.
Nothing in this document has been staged, committed, or pushed; it is a plan
to review, not an action already taken.

Snapshot: repo currently has 3 tracked files
(`docs/FINAL_DEMO_FREEZE_RECORD.md`, `docs/FINAL_DEMO_GROUND_TRUTH.md`,
`docs/VIDEO4_EVALUATION_PROTOCOL.md` — the last one has an uncommitted
modification predating this pass) and everything else listed below is
currently untracked.

## PUBLIC SOURCE

The application itself, its tests, and its build/run tooling.

- `app/` — every subdirectory **except** `app/research/` (see RESEARCH /
  INCLUDE below): `api/`, `pipeline/`, `vision/`, `tracking/`, `events/`,
  `biomechanics/`, `analytics/`, `annotation/`, `storage/`, plus
  `config.py`, `logging_config.py`, `main.py`.
- `frontend/index.html`, `frontend/static/css/main.css`,
  `frontend/static/js/*.js`, `frontend/static/favicon.svg`.
- `tests/` — every file **except** `tests/research/` (see RESEARCH /
  INCLUDE): `test_analytics.py`, `test_api.py`,
  `test_ball_rim_detector_rfdetr.py`, `test_biomechanics_metrics.py`,
  `test_coaching.py`, `test_episode_release_detector.py`,
  `test_export_demo.py`, `test_frontend_regressions.py`, `test_geometry.py`,
  `test_hoop_corroboration.py`, `test_integration_synthetic.py`,
  `test_job_lifecycle.py`, `test_near_hoop_enrichment.py`,
  `test_orchestrator_detector_selection.py`,
  `test_pose_at_arm_corroboration.py`, `test_release_detector.py`,
  `test_release_event_detector.py`, `test_rim_calibration.py`,
  `test_shot_segmentation_phantom_touch.py`, `test_shot_state_machine.py`,
  `test_stats_utils.py`, `test_tracking.py`,
  `test_trajectory_shot_detector.py`, `__init__.py`.
- Operational scripts actually used to run/build/maintain the app:
  `scripts/setup_env.ps1`, `scripts/download_models.py`,
  `scripts/export_demo.py`, `scripts/diagnose_video.py`,
  `scripts/create_final_demo_session.py`, `scripts/range_http_server.py`
  (QA-only static server), `scripts/browser_qa.py` (QA-only Playwright
  driver), `scripts/capture_readme_screenshots.py` (QA-only screenshot
  tool).
- Root config/run files: `README.md`, `LICENSE`, `.gitignore`,
  `pytest.ini`, `requirements.txt`, `run.ps1`.

## PUBLIC DOCS

- `README.md` (listed above; the primary entry point).
- `docs/METHODOLOGY.md` — the full, current, user-facing methodology
  reference; shipped verbatim into the demo export.
- `docs/FINAL_DEMO_GROUND_TRUTH.md` *(already tracked)* — the frozen
  ground-truth table the verified demo outcomes are checked against; core
  to the project's own integrity story, should stay public.
- `docs/FINAL_DEMO_FREEZE_RECORD.md` *(already tracked)*.
- `docs/SHOWCASE_SEGMENTATION_FIX.md`, `docs/FINAL_ARCHITECTURE_DECISION.md`,
  `docs/VIDEO4_EVALUATION_PROTOCOL.md` *(tracked, has an uncommitted
  modification predating this pass — review that diff before staging)*,
  `docs/VIDEO4_FORENSIC_ANALYSIS.md` — referenced directly by README's
  "Evaluation & Limitations" section; removing them would break README
  links.
- `docs/OVERNIGHT_PUBLICATION_READINESS.md`,
  `docs/FINAL_PREPUBLICATION_REPORT.md` (this pass's own report, written
  after this manifest) — process reports, genuinely useful public context
  for a portfolio piece, **but see the redaction note below before
  including them.**

**Redaction done this pass:** `docs/OVERNIGHT_PUBLICATION_READINESS.md`
contained the real local Windows path/username in three places (quoting it
as evidence while reporting the ShuttleSight investigation). Redacted in
place to a generic `<this repo>` / `~\Downloads\...` form that preserves
the finding without the real path — confirmed clean by re-scanning the
file afterward. `docs/FINAL_PREPUBLICATION_REPORT.md` (written after this
manifest) avoids the raw path from the start.

## PUBLIC ASSETS

- `frontend/static/images/hero-basketball.png` (landing-page hero image;
  original asset, not third-party).
- `docs/screenshots/*.png` (all 5 — captured this pass from the real demo,
  see section 8 of the final report).

## GENERATED DEMO

- `dist/` — the exported static demo bundle. **Not committed to `main`** —
  already gitignored, and per the existing plan in
  `docs/DEMO_DEPLOYMENT_AUDIT.md` this is published separately via a
  `gh-pages` branch, not the source history. Regenerated on demand by
  `scripts/export_demo.py`; nothing under it should ever be hand-edited or
  staged directly on `main`.

## LOCAL ONLY

Real, legitimate project content that should stay on this machine (not a
git concern either way — these just shouldn't be manually copied into a
release):

- `data/` (uploads, per-session outputs, SQLite DB, logs, diagnostics,
  datasets, training runs) — already fully gitignored.
- `models/` (`rfdetr_ball_rim_v1.pth`, `yolov8n.pt`, `yolov8s-worldv2.pt`)
  — already gitignored; the checkpoint has its own distribution plan (see
  MODEL DISTRIBUTION below and section N of the final report).
- Root-level raw recordings: `arcvision_demo_01.mov`,
  `arcvision_demo_01_muted.mov`, `arcvision_demo_final.mov`,
  `real_test_01.mp4.mov`, `real_test_02.mp4.mov`, `real_test_03.mov`,
  `real_test_04.mov` — already gitignored (`/*.mov`).
- `.env` — already gitignored; contains the Roboflow API key.

## IGNORED

Already covered by `.gitignore` and not relevant to the publication
decision either way: `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`,
`*.egg-info/`, `.vscode/`, `.claude/` (added this pass).

## RESEARCH / INCLUDE

Code and docs that document real, evaluated-but-not-shipped work. This
project's own credibility rests partly on showing this rather than hiding
it (see README "Evaluation & Limitations" — a failed blind test is reported
there, not omitted), so the default recommendation is to publish these:

- `app/research/` (`net_motion_resolver.py`, `post_contact_reversal.py`)
  and `tests/research/` (their test coverage) — kept together so the
  README's claim that these are "evaluated and never wired into
  production" is independently checkable, not just asserted.
- Research/training/evaluation/forensic scripts explicitly referenced by
  name in README or `docs/METHODOLOGY.md` as the way to reproduce a claim:
  `scripts/train_ball_rim_detector.py`,
  `scripts/train_ball_rim_detector_v2_hardneg.py`,
  `scripts/train_ball_rim_detector_v3.py`,
  `scripts/prepare_ball_rim_dataset.py`,
  `scripts/download_basketball_dataset.py`,
  `scripts/fetch_ball_rim_annotations.py`,
  `scripts/benchmark_ball_rim_detectors.py`,
  `scripts/visual_benchmark_frames.py`,
  `scripts/build_hard_negative_dataset.py`,
  `scripts/build_hard_negative_dataset_v3.py`,
  `scripts/build_merged_dataset_v2_hardneg.py`,
  `scripts/build_merged_dataset_v3.py`, `scripts/_rfdetr_compat.py`.
- The remaining diagnostic/shadow-mode/forensic one-off scripts
  (`scripts/shadow_mode_*.py`, `scripts/forensic_*.py`,
  `scripts/diagnose_*.py`, `scripts/net_motion_shadow_eval*.py`,
  `scripts/shadow_post_contact_reversal_eval.py`,
  `scripts/eval_coverage_v1v2v3.py`, `scripts/eval_coverage_v4.py`,
  `scripts/overnight_v1v2v3v4_regression.py`,
  `scripts/regression_check_torso_enrichment_fix.py`,
  `scripts/audit_transition_duration.py`,
  `scripts/compare_pose_models.py`, `scripts/plot_rim_interactions.py`,
  `scripts/extract_rim_interaction_clips.py`,
  `scripts/dump_frame_signals.py`, `scripts/shot_timeline_debug.py`,
  `scripts/debug_hoop_detector.py`,
  `scripts/diagnose_fallback_corroboration.py`,
  `scripts/backfill_coaching.py`) — the investigation trail behind the
  documented decisions (e.g. `docs/FINAL_ARCHITECTURE_DECISION.md`,
  `docs/SHOWCASE_SEGMENTATION_FIX.md`). Kept for the same transparency
  reason. **This is a content-curation judgment call, not a technical
  requirement** — if the user would rather keep the repo leaner and drop
  some of these, that's a legitimate alternative; nothing here contains
  secrets or personal paths (confirmed by the scan in section P of the
  final report either way).
- The remaining `docs/*.md` research/audit reports not already listed
  under PUBLIC DOCS: `docs/ARCVISION_DEMO_ENGINEERING_PASS.md`,
  `docs/ARCVISION_REDESIGN_PLAN.md`, `docs/DEMO_DEPLOYMENT_AUDIT.md`,
  `docs/FINAL_DEMO_BLIND_EVALUATION.md`,
  `docs/FINAL_DEMO_RECORDING_PROTOCOL.md`,
  `docs/FINAL_DEMO_RELIABILITY_FORENSIC.md`,
  `docs/MADE_SEARCH_COMPLETENESS_FIX.md`, `docs/NET_MOTION_SHADOW.md`,
  `docs/OUTCOME_NEXT_REPRESENTATION_DECISION.md`,
  `docs/OUTCOME_PHYSICAL_EVIDENCE_FORENSIC.md`,
  `docs/OUTCOME_VISUAL_INFORMATION_AUDIT.md`,
  `docs/POST_CONTACT_REVERSAL_SHADOW.md`.

## RESEARCH / EXCLUDE

- `docs/PUBLICATION_PREFLIGHT.md`, `docs/FINAL_SHIPPING_AUDIT.md` — both
  contain the real local Windows path/username in prose (confirmed this
  pass and the overnight pass). Both are also superseded, dated snapshots
  of earlier readiness passes (e.g. `PUBLICATION_PREFLIGHT.md` still
  describes the old 7-shot demo and session `3809b2b304064f21`, long
  superseded). Recommend keeping these **local only** rather than
  redacting-and-publishing, since their content value is fully superseded
  by `docs/OVERNIGHT_PUBLICATION_READINESS.md` /
  `docs/FINAL_PREPUBLICATION_REPORT.md` anyway.

## MODEL DISTRIBUTION

- `models/rfdetr_ball_rim_v1.pth` — **not staged, not committed, not
  uploaded during this pass.** See section N of the final report for the
  full plan (GitHub Release asset, checksum, recommended description).
  Distribution happens after a repo exists, as its own separate,
  deliberate step — never folded into the source-publication commit.

## SHUTTLESIGHT / NEVER INCLUDE

- `ShuttleSight/` (nested directory, its own separate `.git`, zero commits,
  unrelated project) — **must never appear in any ArcVision commit.**
  Already covered by a dedicated `.gitignore` entry (`/ShuttleSight/`,
  added during the overnight pass) as a safety net on top of simply never
  `git add`-ing it. See section O of the final report for its current
  status and the safe move procedure for later (not performed this pass).
