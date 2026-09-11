"""
Compatibility shim letting RF-DETR's official training pipeline
(model.train(), the real PyTorch Lightning trainer/callbacks/checkpointing)
run on a machine where Windows Smart App Control blocks
`faster_coco_eval`'s compiled evaluation extension (confirmed via Windows
Event Log Code Integrity events: the .pyd "did not meet the Enterprise
signing level requirements").

RF-DETR's training package unconditionally imports `faster_coco_eval` at
module load time (rfdetr/evaluation/coco_eval.py), purely to build a
`CocoEvaluator` class that is dead code for a plain bbox (non-keypoint,
non-segmentation) model -- the actual mAP computation RF-DETR's
COCOEvalCallback performs at runtime goes through
`torchmetrics.detection.MeanAveragePrecision`, which itself natively
supports a `backend="pycocotools"` mode (in fact its own default) that
needs no faster_coco_eval at all and is fully functional on this machine.

The `faster_coco_eval` stand-in itself lives in
`.venv/Lib/site-packages/sitecustomize.py`, not here -- it must be visible
to every Python process using this venv, including the fresh interpreters
PyTorch DataLoader workers spawn on Windows ("spawn" start method
re-executes the whole interpreter startup sequence, so a sys.modules patch
applied only in this main process never reaches them; sitecustomize.py is
auto-imported by every one of them, this shim only needs to run in the
main process). This module handles the second half:

  Monkey-patches `MeanAveragePrecision` as seen by
  rfdetr.training.callbacks.coco_eval so any request for
  backend="faster_coco_eval" is transparently redirected to the
  already-verified-working backend="pycocotools" instead.

Everything else about RF-DETR's training run (the Lightning trainer, the
model, the optimizer/scheduler, checkpointing, early stopping, the actual
detection loss) is completely untouched -- this only substitutes one
evaluation backend for another, functionally equivalent one.

Call apply() once, before importing anything else from `rfdetr`.
"""
from __future__ import annotations


def _patch_coco_eval_callback_to_pycocotools() -> None:
    from rfdetr.training.callbacks import coco_eval as ce_mod
    from torchmetrics.detection import MeanAveragePrecision as _RealMAP

    if getattr(_RealMAP, "_formai_patched_backend", False):
        return

    class _PycocotoolsMAP(_RealMAP):
        _formai_patched_backend = True

        def __init__(self, *args, **kwargs):
            kwargs["backend"] = "pycocotools"
            super().__init__(*args, **kwargs)

    ce_mod.MeanAveragePrecision = _PycocotoolsMAP


def apply() -> None:
    """Idempotent; safe to call multiple times."""
    import rfdetr.training  # noqa: F401  (import succeeds -- faster_coco_eval stub is installed by sitecustomize.py)
    _patch_coco_eval_callback_to_pycocotools()
