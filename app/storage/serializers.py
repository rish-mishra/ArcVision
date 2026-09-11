"""
Converts pipeline result dataclasses (ShotRecord, SessionResult, analytics
reports) into plain JSON-safe dicts for API responses and SQLite storage.
Kept separate from the dataclasses themselves so the pipeline internals
don't need to know anything about JSON or the API/storage layer.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any


def to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if dataclasses.is_dataclass(obj):
        return {k: to_jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return {k: to_jsonable(v) for k, v in vars(obj).items()}
    return str(obj)


def serialize_shot(shot) -> dict:
    d = to_jsonable(shot)
    # overall_confidence_level is a computed @property (min of release/pose/
    # ball-track confidence, bucketed via the same Confidence.from_score
    # used elsewhere), not a dataclass field, so dataclasses.asdict inside
    # to_jsonable doesn't pick it up on its own -- add it explicitly.
    d["overall_confidence_level"] = shot.overall_confidence_level.value
    return d


def serialize_session_result(result) -> dict:
    """Drops the heavy raw per-frame pose/ball arrays -- those are only
    needed transiently to render the annotated video, not for the stored
    session record or the dashboard JSON payload."""
    return {
        "video_meta": {
            "width": result.video_meta.width,
            "height": result.video_meta.height,
            "fps": result.video_meta.fps,
            "duration_sec": result.video_meta.duration_sec,
        },
        "shots": [serialize_shot(s) for s in result.shots],
        "hoop": to_jsonable(result.hoop),
        "session_summary": to_jsonable(result.session_summary),
        "consistency": to_jsonable(result.consistency),
        "makes_vs_misses": to_jsonable(result.makes_vs_misses),
        "trends": to_jsonable(result.trends),
        "findings": to_jsonable(result.findings),
        "coaching": to_jsonable(result.coaching),
        "warnings": result.warnings,
        "analysis_fps": result.analysis_fps,
        "analysis_size": list(result.analysis_size),
    }
