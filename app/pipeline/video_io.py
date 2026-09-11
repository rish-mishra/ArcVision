"""
Video validation and frame access. Everything downstream reads frames
through `FrameReader`, which subsamples to a manageable analysis
resolution/frame-rate so detector inference stays fast on long clips, while
keeping the mapping back to original frame indices/timestamps explicit.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import cv2

from app.config import CONFIG
from app.logging_config import get_logger

log = get_logger("pipeline.video_io")


class VideoValidationError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


@dataclass
class VideoMeta:
    path: Path
    width: int
    height: int
    fps: float
    frame_count: int
    duration_sec: float


def validate_video(path: Path) -> VideoMeta:
    cfg = CONFIG.video
    if path.suffix.lower() not in cfg.allowed_extensions:
        raise VideoValidationError(
            f"Unsupported file type '{path.suffix}'. Supported: {cfg.allowed_extensions}",
            "unsupported_extension",
        )
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > cfg.max_file_size_mb:
        raise VideoValidationError(
            f"File is {size_mb:.0f}MB, exceeds the {cfg.max_file_size_mb}MB limit.",
            "file_too_large",
        )

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoValidationError("File could not be opened as a video (corrupt or unsupported codec).",
                                     "unreadable_video")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    if width <= 0 or height <= 0:
        raise VideoValidationError("Video has no readable frames.", "no_frames")
    if width < cfg.min_width or height < cfg.min_height:
        raise VideoValidationError(
            f"Resolution {width}x{height} is below the minimum {cfg.min_width}x{cfg.min_height}.",
            "resolution_too_low",
        )
    duration = frame_count / fps if fps > 0 else 0.0
    if fps <= 0 or frame_count <= 0:
        raise VideoValidationError("Could not determine video frame rate/frame count.", "bad_metadata")
    if duration < cfg.min_duration_sec:
        raise VideoValidationError(f"Video is only {duration:.1f}s; too short to analyze.", "too_short")
    if duration > cfg.max_duration_sec:
        raise VideoValidationError(
            f"Video is {duration:.0f}s, exceeds the {cfg.max_duration_sec:.0f}s limit for a single session.",
            "too_long",
        )

    return VideoMeta(path=path, width=width, height=height, fps=fps,
                       frame_count=frame_count, duration_sec=duration)


@dataclass
class AnalysisFrame:
    frame_index: int          # index within the subsampled analysis sequence
    source_frame_index: int   # index in the ORIGINAL video
    timestamp_sec: float
    image: "any"               # np.ndarray, BGR, at analysis resolution


class FrameReader:
    """
    Iterates a video at a reduced resolution/frame-rate for analysis.
    `source_frame_index`/`timestamp_sec` are always relative to the
    ORIGINAL video, so annotation can later map back precisely.
    """

    def __init__(self, meta: VideoMeta, cfg=None):
        self.meta = meta
        self.cfg = cfg or CONFIG.video
        self.scale = 1.0
        longer_side = max(meta.width, meta.height)
        if longer_side > self.cfg.analysis_max_dim:
            self.scale = self.cfg.analysis_max_dim / longer_side
        self.analysis_width = int(round(meta.width * self.scale))
        self.analysis_height = int(round(meta.height * self.scale))
        self.frame_stride = max(1, round(meta.fps / self.cfg.analysis_target_fps))
        self.effective_fps = meta.fps / self.frame_stride

    def __iter__(self) -> Iterator[AnalysisFrame]:
        cap = cv2.VideoCapture(str(self.meta.path))
        try:
            src_idx = 0
            analysis_idx = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if src_idx % self.frame_stride == 0:
                    if self.scale != 1.0:
                        frame = cv2.resize(frame, (self.analysis_width, self.analysis_height),
                                             interpolation=cv2.INTER_AREA)
                    ts = src_idx / self.meta.fps
                    yield AnalysisFrame(analysis_idx, src_idx, ts, frame)
                    analysis_idx += 1
                src_idx += 1
        finally:
            cap.release()


def transcode_to_browser_mp4(input_path: Path, output_path: Path) -> None:
    """Re-encodes with libx264 + yuv420p via bundled ffmpeg so every
    modern browser can play it back (OpenCV's mp4v/avc1 writer output is
    not reliably seekable/playable in <video> tags)."""
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y", "-i", str(input_path),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("ffmpeg transcode failed: %s", result.stderr[-2000:])
        raise RuntimeError("Failed to encode browser-compatible video output.")
