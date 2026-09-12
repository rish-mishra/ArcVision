"""
The single frozen ground-truth source for the featured public demo session,
shared by scripts/export_demo.py (applies it to the exported analytics
payload) and scripts/regenerate_featured_demo_replay_labels.py (applies it to
the exported replay video's burned-in outcome labels) -- split into its own
module, rather than one of those two importing it from the other, so neither
script has to import the other (export_demo.py needs to be able to call into
the regeneration script; the regeneration script importing back from
export_demo.py would make that a circular import).
"""
from __future__ import annotations

# The one session this bundle demonstrates -- a real, already-analyzed
# session, approved for this purpose. Change here only if you deliberately
# choose a different already-completed session; export_demo.py never picks
# one automatically. Currently arcvision_demo_final.mov -- the frozen final
# showcase recording (11 shots, ground truth recorded BEFORE inference in
# docs/FINAL_DEMO_GROUND_TRUTH.md, blind-evaluated in
# docs/FINAL_DEMO_BLIND_EVALUATION.md). Superseded TWO earlier session ids
# this pointed to before: arcvision_demo_01_muted.mov's 3809b2b304064f21
# (a different, older showcase video), and then 29c7e751775e4f20 (this same
# video, but analyzed before this session's segmentation fix -- see
# docs/SHOWCASE_SEGMENTATION_FIX.md -- so it still had 13 detected windows
# including 2 false positives; export_demo.py's own shot-count safety check
# refused to export it once VERIFIED_OUTCOMES_BY_SHOT_INDEX below expected
# exactly 11). This id (ab556626332b440e, via
# scripts/create_final_demo_session.py) is a fresh run of the same source
# video under current, post-segmentation-fix production code: 11/11 shots,
# 0 false positives, 0 false negatives.
DEMO_SESSION_ID = "fee1c3bcd7b84322"

# Frozen ground truth for arcvision_demo_final.mov, copied verbatim from
# docs/FINAL_DEMO_GROUND_TRUTH.md -- recorded by the user from manual review
# of the raw video BEFORE ArcVision inference ever ran on it. This mapping is
# applied ONLY to DEMO_SESSION_ID's exported payload and replay video, never
# in app/ (the production pipeline never sees or uses it, and no other
# session -- local or otherwise -- is ever touched by it).
VERIFIED_OUTCOMES_BY_SHOT_INDEX = {
    1: "made", 2: "made", 3: "made", 4: "made", 5: "missed",
    6: "made", 7: "made", 8: "missed", 9: "missed", 10: "made", 11: "made",
}
