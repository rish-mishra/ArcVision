"""
Builds a BALL/RIM-only training dataset from the University of Arizona
"Basketball Shooting Robot" Roboflow project (CC BY 4.0), bypassing the
one generated/downloadable version -- which turned out to include ONLY the
`rim` class (confirmed: the exported version's 10,140 rim annotations
match the raw workspace's rim total exactly, and it has zero ball/
basketball annotations at all). The raw workspace itself does have both
(`ball`: 4522, `basketball`: 2900 annotations, per `project.classes`), so
this script pulls those directly from the source project via Roboflow's
per-image search/detail API and the public per-image CDN URL, rather than
substituting a different, less appropriate dataset.

Reads ROBOFLOW_API_KEY from .env via python-dotenv -- never printed/logged.

Resumable: writes one manifest JSON per image under
data/datasets/basketball_ball_rim_manifest/, and skips any image whose
manifest file and downloaded image both already exist, so an interrupted
run can just be re-launched.

Usage:
    .venv\\Scripts\\python scripts\\fetch_ball_rim_annotations.py
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = ROOT / "data" / "datasets" / "basketball_ball_rim_images"
MANIFEST_DIR = ROOT / "data" / "datasets" / "basketball_ball_rim_manifest"
ID_CACHE_PATH = ROOT / "data" / "datasets" / "basketball_ball_rim_ids.json"
WORKSPACE = "the-university-of-arizona-th1yv"
PROJECT = "basketball-shooting-robot"
RELEVANT_CLASSES = ("ball", "basketball", "rim")
MAX_WORKERS = 12
PAGE_LIMIT = 200
MAX_RETRIES = 4


def _with_retries(fn, *args, **kwargs):
    """This dataset fetch makes several thousand network calls, and a
    transient connection reset (confirmed to happen at least once against
    Roboflow's API during this run) would otherwise abort the whole
    enumeration or a single image fetch outright. Retries with a short
    exponential backoff before giving up for real."""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(1.5 * (2 ** attempt))
    raise last_exc


def _list_relevant_image_ids(project) -> dict:
    """Returns {image_id: search-result-dict} for every image annotated
    with at least one of ball/basketball/rim, deduplicated across classes.
    Cached to disk so a crash/connection-reset during this step (a real
    risk seen with several thousand paginated requests) doesn't force
    starting the enumeration itself over from scratch."""
    if ID_CACHE_PATH.exists():
        cached = json.loads(ID_CACHE_PATH.read_text(encoding="utf-8"))
        print(f"  using cached id list: {len(cached)} image(s)")
        return cached

    found = {}
    for cls in RELEVANT_CLASSES:
        offset = 0
        while True:
            page = list(_with_retries(project.search, class_name=cls, offset=offset,
                                        limit=PAGE_LIMIT, fields=["id", "name"]))
            if not page:
                break
            for item in page:
                found[item["id"]] = item
            offset += PAGE_LIMIT
            if len(page) < PAGE_LIMIT:
                break
        print(f"  class '{cls}': {len(found)} cumulative unique image(s) so far", flush=True)

    tmp_path = ID_CACHE_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(found), encoding="utf-8")
    os.replace(tmp_path, ID_CACHE_PATH)
    return found


def _fetch_one(project, image_id: str) -> dict | None:
    manifest_path = MANIFEST_DIR / f"{image_id}.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    details = _with_retries(project.image, image_id)
    ann = details.get("annotation") or {}
    boxes = [b for b in ann.get("boxes", []) if b["label"] in RELEVANT_CLASSES]
    if not boxes:
        return None  # e.g. an image that matched search but whose only relevant box was later edited out

    image_path = IMAGES_DIR / f"{image_id}.jpg"
    if not image_path.exists():
        url = details["urls"]["original"]

        def _download():
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            return resp.content

        content = _with_retries(_download)
        tmp_image_path = image_path.with_suffix(".jpg.tmp")
        tmp_image_path.write_bytes(content)
        os.replace(tmp_image_path, image_path)

    record = {
        "image_id": image_id,
        "file_name": image_path.name,
        "width": ann.get("width"),
        "height": ann.get("height"),
        "split": details.get("split", "train"),
        "boxes": [
            {"label": b["label"], "cx": float(b["x"]), "cy": float(b["y"]),
              "w": float(b["width"]), "h": float(b["height"])}
            for b in boxes
        ],
    }
    # Atomic write: a same-filesystem rename can't leave a torn/empty file
    # behind if the process is killed mid-write (confirmed real risk after
    # an OS crash left ~360 zero-byte manifest files from a plain
    # write_text call).
    tmp_path = manifest_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(record), encoding="utf-8")
    os.replace(tmp_path, manifest_path)
    return record


def main():
    load_dotenv()
    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        print("ROBOFLOW_API_KEY not found in environment/.env. Aborting.")
        sys.exit(1)

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    from roboflow import Roboflow
    rf = Roboflow(api_key=api_key)
    project = rf.workspace(WORKSPACE).project(PROJECT)

    print("Enumerating images with ball/basketball/rim annotations...", flush=True)
    relevant = _list_relevant_image_ids(project)
    print(f"Total relevant images to fetch: {len(relevant)}", flush=True)

    ok, empty, errors = 0, 0, 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, project, iid): iid for iid in relevant}
        for i, fut in enumerate(as_completed(futures), 1):
            iid = futures[fut]
            try:
                rec = fut.result()
                if rec is None:
                    empty += 1
                else:
                    ok += 1
            except Exception as e:
                errors += 1
                print(f"  ERROR fetching {iid}: {type(e).__name__}: {e}", flush=True)
            if i % 200 == 0:
                elapsed = time.time() - t0
                print(f"  progress: {i}/{len(relevant)} ({elapsed:.0f}s elapsed, ok={ok} empty={empty} errors={errors})",
                       flush=True)

    print(f"Done. ok={ok} empty={empty} errors={errors} total_time={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
