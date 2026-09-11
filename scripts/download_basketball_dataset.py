"""
Downloads the University of Arizona "Basketball Shooting Robot" dataset
(Roboflow Universe, CC BY 4.0, ~9.8k images) in COCO format.

Reads ROBOFLOW_API_KEY from .env via python-dotenv -- this script never
prints, logs, or otherwise exposes the key value. Do not modify this
script to print os.environ or the `rf` client object's repr, since some
SDK objects embed the key in their string representation.

Usage:
    .venv\\Scripts\\python scripts\\download_basketball_dataset.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
import os

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "datasets" / "basketball_shooting_robot_raw"
WORKSPACE = "the-university-of-arizona-th1yv"
PROJECT = "basketball-shooting-robot"


def main():
    load_dotenv()
    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        print("ROBOFLOW_API_KEY not found in environment/.env. Aborting without attempting download.")
        sys.exit(1)

    from roboflow import Roboflow
    rf = Roboflow(api_key=api_key)
    project = rf.workspace(WORKSPACE).project(PROJECT)

    versions = project.versions()
    if not versions:
        print("No published versions found for this project.")
        sys.exit(1)
    latest = versions[-1]
    print(f"Using dataset version: {latest.version}")

    # Roboflow's SDK treats an already-EXISTING target directory as "already
    # downloaded" and silently skips the actual fetch unless overwrite=True
    # -- do not pre-create OUTPUT_DIR before calling download().
    dataset = latest.download("coco", location=str(OUTPUT_DIR), overwrite=True)
    print(f"Downloaded to: {dataset.location}")


if __name__ == "__main__":
    main()
