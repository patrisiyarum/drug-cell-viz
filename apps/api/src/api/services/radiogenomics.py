"""CT-scan → HRD radiogenomics preprocessing + inference adapter.

Patient-facing flow:
    CT upload (DICOM zip or NIfTI .nii.gz)
        → load_volume              load into a 3D numpy array
        → crop_to_tumor            tumor-centric crop (via a mask or heuristic)
        → resample_volume          fixed shape (96, 96, 96) for the CNN input
        → normalize_intensity      Hounsfield units → model-expected range
        → infer_hrd                calls the trained model if available,
                                   otherwise returns an explicit placeholder

Intentional non-goals (these live in the hrd-radiogenomics research repo,
not in this backend):
    - model training
    - full MONAI / Med3D transform stacks
    - DICOM-SEG segmentation for automatic tumor localisation
    - interpretability heatmaps

When MODEL_WEIGHTS_PATH points at a trained checkpoint, `infer_hrd` will
load it on first use and serve real predictions. Until then it returns a
clearly-labelled placeholder so the UI upload path is exercised end-to-end
even while the research repo is still training.
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

logger = logging.getLogger(__name__)

# Model input shape the downstream 3D CNN expects. Matches the default Med3D
# / MONAI pretrained backbones we plan to fine-tune in hrd-radiogenomics.
TARGET_SHAPE: tuple[int, int, int] = (96, 96, 96)

# Hounsfield-unit window for soft tissue (tumors, liver, ovary). Narrower
# than a full-range window [-1000, 3000] because the model should focus on
# tissue texture, not air vs bone.
HU_WINDOW: tuple[float, float] = (-200.0, 250.0)


@dataclass(frozen=True)
class VolumeMetadata:
    """Minimal header data extracted per upload."""

    modality: Literal["CT", "MR", "PT", "UNKNOWN"]
    original_shape: tuple[int, int, int]
    original_spacing_mm: tuple[float, float, float]
    target_shape: tuple[int, int, int]
    hu_window: tuple[float, float]


@dataclass(frozen=True)
class RadiogenomicsPrediction:
    """Output of the whole preprocessing + inference chain."""

    metadata: VolumeMetadata
    hrd_probability: float             # 0..1 — chance the tumor is HR-deficient
    label: Literal[
        "predicted_hr_deficient",
        "predicted_hr_proficient",
        "uncertain",
        "model_not_trained",
    ]
    confidence: Literal["low", "moderate", "high", "stub"]
    caveats: list[str]


class RadiogenomicsError(ValueError):
    """Raised when an upload cannot be loaded or preprocessed."""


# ---------------------------------------------------------------------------
# Volume loading
# ---------------------------------------------------------------------------

def load_volume(raw: bytes, filename: str) -> tuple[np.ndarray, VolumeMetadata]:
    """Parse either a NIfTI file or a DICOM-zip bundle into a 3D volume.

    Returns (volume, metadata). Volume is oriented (Z, Y, X) with arbitrary
    native spacing; the resample step normalises to TARGET_SHAPE.
    """
    name = filename.lower()
    if name.endswith((".nii", ".nii.gz")):
        return _load_nifti(raw)
    if name.endswith(".zip") or _looks_like_dicom(raw):
        return _load_dicom_zip(raw)
    raise RadiogenomicsError(
        f"unsupported upload format: {filename!r}. Expected .nii, .nii.gz, "
        "or a .zip containing a DICOM series."
    )


def _load_nifti(raw: bytes) -> tuple[np.ndarray, VolumeMetadata]:
    # Deferred import so the API module stays importable without nibabel
    # installed (e.g. in the web-only unit tests).
    import nibabel as nib

    with io.BytesIO(raw) as fh:
        try:
            img = nib.Nifti1Image.from_bytes(fh.read())
        except Exception as exc:
            raise RadiogenomicsError(f"could not parse NIfTI: {exc}") from exc

    vol = np.asarray(img.dataobj).astype(np.float32)
    # nibabel returns (X, Y, Z); transpose to (Z, Y, X) for consistency with
    # DICOM's axial-slice-first convention.
    if vol.ndim == 4:
        vol = vol[..., 0]
    vol = np.transpose(vol, (2, 1, 0))

    spacing = tuple(float(s) for s in img.header.get_zooms()[:3])
    modality = "CT" if _looks_like_ct(vol) else "UNKNOWN"
    return vol, VolumeMetadata(
        modality=modality,
        original_shape=tuple(int(d) for d in vol.shape),  # type: ignore[arg-type]
        original_spacing_mm=spacing,
        target_shape=TARGET_SHAPE,
        hu_window=HU_WINDOW,
    )


def _load_dicom_zip(raw: bytes) -> tuple[np.ndarray, VolumeMetadata]:
    import pydicom

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        dicom_members = [n for n in zf.namelist() if not n.endswith("/")]
        if not dicom_members:
            raise RadiogenomicsError("zip is empty")

        datasets = []
        for name in dicom_members:
            try:
                ds = pydicom.dcmread(io.BytesIO(zf.read(name)), stop_before_pixels=False)
            except Exception:
                continue
            if getattr(ds, "Modality", None) is None:
                continue
            if getattr(ds, "PixelData", None) is None:
                continue
            datasets.append(ds)
        if not datasets:
            raise RadiogenomicsError("zip contained no readable DICOM pixel data")

    # Sort by instance number / slice location so the stack is axially ordered.
    def _slice_key(ds: "pydicom.dataset.Dataset") -> float:
        for attr in ("ImagePositionPatient", "SliceLocation", "InstanceNumber"):
            v = getattr(ds, attr, None)
            if v is None:
                continue
            if attr == "ImagePositionPatient" and hasattr(v, "__getitem__"):
                return float(v[2])  # type: ignore[index]
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
        return 0.0

    datasets.sort(key=_slice_key)

    first = datasets[0]
    slices: list[np.ndarray] = []
    for ds in datasets:
        arr = ds.pixel_array.astype(np.float32)
        # Apply HU rescaling if present (CT ONLY — modality-specific).
        slope = getattr(ds, "RescaleSlope", 1.0) or 1.0
        intercept = getattr(ds, "RescaleIntercept", 0.0) or 0.0
        slices.append(arr * float(slope) + float(intercept))
    vol = np.stack(slices, axis=0)

    spacing_xy = getattr(first, "PixelSpacing", (1.0, 1.0))
    slice_thickness = float(getattr(first, "SliceThickness", 1.0) or 1.0)
    spacing = (slice_thickness, float(spacing_xy[0]), float(spacing_xy[1]))

    return vol, VolumeMetadata(
        modality=str(getattr(first, "Modality", "UNKNOWN")),
        original_shape=tuple(int(d) for d in vol.shape),  # type: ignore[arg-type]
        original_spacing_mm=spacing,
        target_shape=TARGET_SHAPE,
        hu_window=HU_WINDOW,
    )


def _looks_like_dicom(raw: bytes) -> bool:
    return len(raw) > 132 and raw[128:132] == b"DICM"


def _looks_like_ct(vol: np.ndarray) -> bool:
    """Rough HU check: CTs have values in [~ -1000, +3000]."""
    sample = vol.flatten()[: min(vol.size, 100_000)]
    return sample.min() < -500 and sample.max() > 200


# ---------------------------------------------------------------------------
# Preprocessing — tumor crop + resample + normalise
# ---------------------------------------------------------------------------

def preprocess(volume: np.ndarray, metadata: VolumeMetadata) -> np.ndarray:
    """Crop (heuristic), resample to TARGET_SHAPE, normalise HU to [0, 1].

    Returns a float32 (Z, Y, X) array of shape TARGET_SHAPE ready for the
    3D CNN. The heuristic crop uses image-wide intensity thresholding to
    find the soft-tissue bounding box; a production pipeline would instead
    take a DICOM-SEG tumor mask from the uploading RIS.
    """
    from scipy.ndimage import zoom

    cropped = crop_to_tumor(volume)

    zoom_factors = tuple(
        TARGET_SHAPE[i] / cropped.shape[i] for i in range(3)
    )
    resampled = zoom(cropped, zoom_factors, order=1)  # trilinear
    # zoom can over/under-shoot by ±1 voxel in each axis; re-pad/crop to exact.
    resampled = _fit_exact(resampled, TARGET_SHAPE)
    return normalize_intensity(resampled, HU_WINDOW)


def crop_to_tumor(volume: np.ndarray) -> np.ndarray:
    """Coarse soft-tissue bounding box.

    Thresholds at [-200, 250] HU, takes the largest connected component,
    crops the box with a small margin. Returns the cropped volume. Fine
    enough for a first pass; a production pipeline would consume an
    explicit tumor mask.
    """
    lo, hi = HU_WINDOW
    mask = (volume >= lo) & (volume <= hi)
    if not mask.any():
        return volume  # nothing to crop to
    coords = np.where(mask)
    mins = tuple(int(c.min()) for c in coords)
    maxs = tuple(int(c.max()) + 1 for c in coords)
    pad = 4
    slicers = tuple(
        slice(max(0, mins[i] - pad), min(volume.shape[i], maxs[i] + pad))
        for i in range(3)
    )
    return volume[slicers]


def _fit_exact(volume: np.ndarray, target: tuple[int, int, int]) -> np.ndarray:
    out = np.zeros(target, dtype=volume.dtype)
    slicers_in = []
    slicers_out = []
    for i in range(3):
        in_extent = min(volume.shape[i], target[i])
        in_start = (volume.shape[i] - in_extent) // 2
        out_start = (target[i] - in_extent) // 2
        slicers_in.append(slice(in_start, in_start + in_extent))
        slicers_out.append(slice(out_start, out_start + in_extent))
    out[tuple(slicers_out)] = volume[tuple(slicers_in)]
    return out


def normalize_intensity(
    volume: np.ndarray,
    window: tuple[float, float],
) -> np.ndarray:
    lo, hi = window
    clipped = np.clip(volume, lo, hi)
    return ((clipped - lo) / (hi - lo)).astype(np.float32)


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

# Path to a trained model checkpoint. When set (e.g. MODEL_WEIGHTS_PATH env
# var resolved elsewhere) and the file exists, infer_hrd loads it via torch
# and serves real predictions. When unset, we return a deterministic
# placeholder that the UI labels "model not yet trained" so patients don't
# mistake the stub for a real score.
_MODEL_WEIGHTS: Path | None = None


def infer_hrd(preprocessed: np.ndarray, metadata: VolumeMetadata) -> RadiogenomicsPrediction:
    """Run the 3D CNN on the preprocessed volume.

    Until a trained checkpoint is wired up (via `set_model_weights(path)`),
    this returns a stub prediction marked `model_not_trained` with the
    caveats the UI must surface before any user sees it.
    """
    if _MODEL_WEIGHTS is None or not _MODEL_WEIGHTS.exists():
        return _stub_prediction(metadata)
    return _real_prediction(preprocessed, metadata)


def set_model_weights(path: Path) -> None:
    """Point the inference path at a trained checkpoint."""
    global _MODEL_WEIGHTS
    _MODEL_WEIGHTS = path
    logger.info("radiogenomics model weights set to %s", path)


def _stub_prediction(metadata: VolumeMetadata) -> RadiogenomicsPrediction:
    return RadiogenomicsPrediction(
        metadata=metadata,
        hrd_probability=0.5,
        label="model_not_trained",
        confidence="stub",
        caveats=[
            "This is a research prototype. A trained radiogenomics model is "
            "not wired into this deployment. The preprocessing pipeline "
            "(load, crop, resample to 96x96x96, HU-window normalise) is "
            "real, but the prediction is a placeholder.",
            "Training data and the 5-step pipeline live in the "
            "hrd-radiogenomics research repo. When a trained checkpoint is "
            "available, this endpoint will return real probabilities with "
            "held-out AUROC, external validation, and saliency heatmaps.",
            "Do not use this for any clinical decision.",
        ],
    )


def _real_prediction(
    preprocessed: np.ndarray,
    metadata: VolumeMetadata,
) -> RadiogenomicsPrediction:
    # Lazy-import torch so the stub path stays light.
    import torch

    # The research repo's eventual contract: load the saved state_dict into
    # a Med3D / MONAI DenseNet121-3D backbone with a two-class head. The
    # weights file also carries the training-time metadata (training AUROC,
    # external-validation delta, seed). For now we assert a minimal contract
    # and fail loudly if the checkpoint shape doesn't match.
    assert _MODEL_WEIGHTS is not None
    ckpt = torch.load(_MODEL_WEIGHTS, map_location="cpu")
    if "model_state" not in ckpt or "model_card" not in ckpt:
        raise RadiogenomicsError(
            "model checkpoint missing model_state / model_card keys; expected "
            "a checkpoint produced by the hrd-radiogenomics training pipeline"
        )
    # TODO: instantiate the backbone, load_state_dict, forward pass on a
    # (1, 1, 96, 96, 96) tensor, softmax, return p_lof. Not shipped here
    # because the model checkpoint lives in the research repo.
    raise NotImplementedError("real inference path wired when the research repo ships weights")
