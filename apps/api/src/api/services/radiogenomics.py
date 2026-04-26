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
    if name.endswith(".tcia"):
        # NBIA Data Retriever manifest. Tiny text file that lists series UIDs;
        # we fetch the first series from TCIA on the user's behalf so the
        # uploaded manifest "just works" instead of failing with a confusing
        # "what's this?" error.
        return _load_tcia_manifest(raw)
    if name.endswith(".zip") or _looks_like_dicom(raw):
        return _load_dicom_zip(raw)
    raise RadiogenomicsError(
        f"unsupported upload format: {filename!r}. Expected .nii, .nii.gz, "
        ".tcia (NBIA manifest), or a .zip containing a DICOM series."
    )


def _load_tcia_manifest(raw: bytes) -> tuple[np.ndarray, VolumeMetadata]:
    """Parse an NBIA `.tcia` manifest, fetch the first series from TCIA,
    and load it as if the user had uploaded the DICOM zip directly.

    Manifest format (NBIA Data Retriever v3):
        downloadServerUrl=...
        includeAnnotation=true
        databasketId=...
        manifestVersion=3.0
        ListOfSeriesToDownload=
        1.2.840.113619.2.55.3.604688119.971.1259600000.123
        1.2.840.113619.2.55.3.604688119.971.1259600000.456
        ...

    We fetch the first series by default (a typical TCGA-OV manifest
    bundles axial + scout; the axial is usually first and is what the
    radiogenomics model wants anyway). If the manifest is malformed or
    TCIA returns nothing, raise a RadiogenomicsError with a clear message.
    """
    import requests

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        raise RadiogenomicsError(f"could not decode .tcia manifest: {exc}") from exc

    # Walk past the header into the series-UID block.
    series_uids: list[str] = []
    in_block = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.lower().startswith("listofseriestodownload"):
            in_block = True
            continue
        if in_block and "=" not in s:
            series_uids.append(s)

    if not series_uids:
        raise RadiogenomicsError(
            "no series UIDs found in the .tcia manifest. Try downloading the "
            "actual DICOM .zip from TCIA's download options instead of the "
            "NBIA Data Retriever manifest."
        )

    series_uid = series_uids[0]
    logger.info(
        "loading .tcia manifest with %d series; fetching the first one (%s) "
        "from TCIA", len(series_uids), series_uid,
    )

    tcia_endpoint = (
        "https://services.cancerimagingarchive.net/nbia-api/services/v1/getImage"
    )
    try:
        resp = requests.get(
            tcia_endpoint, params={"SeriesInstanceUID": series_uid},
            stream=True, timeout=(15, 600),
        )
        resp.raise_for_status()
        zip_bytes = resp.content
    except Exception as exc:
        raise RadiogenomicsError(
            f"could not fetch series {series_uid} from TCIA: {exc}",
        ) from exc

    if len(zip_bytes) < 1024:
        raise RadiogenomicsError(
            f"TCIA returned an unexpectedly small payload ({len(zip_bytes)} "
            "bytes) for the series in this manifest. Try downloading the "
            "DICOM .zip directly from TCIA's web UI."
        )

    return _load_dicom_zip(zip_bytes)


def _load_nifti(raw: bytes) -> tuple[np.ndarray, VolumeMetadata]:
    # Deferred import so the API module stays importable without nibabel
    # installed (e.g. in the web-only unit tests).
    import gzip

    import nibabel as nib

    # `Nifti1Image.from_bytes` doesn't auto-decompress the gzip wrapper
    # that every `.nii.gz` ships with, so we peel it first if present.
    # Magic bytes 0x1f 0x8b mark the gzip stream start; uncompressed
    # `.nii` starts with a 348-byte int header.
    payload = raw
    if len(raw) >= 2 and raw[0] == 0x1F and raw[1] == 0x8B:
        try:
            payload = gzip.decompress(raw)
        except Exception as exc:
            raise RadiogenomicsError(f"could not decompress NIfTI gzip: {exc}") from exc

    with io.BytesIO(payload) as fh:
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
_MODEL_BACKBONE: str = "monai_densenet"
# Cached loaded model + device so we don't rebuild + reload on every request.
_MODEL = None  # type: ignore[assignment]
_MODEL_DEVICE: str | None = None
# Cached training-time metadata from the checkpoint's model_card so caveats
# and the UI's confidence banner can cite the actual held-out AUROC of the
# loaded fold, not a hardcoded number.
_MODEL_CARD: dict = {}


def infer_hrd(preprocessed: np.ndarray, metadata: VolumeMetadata) -> RadiogenomicsPrediction:
    """Run the 3D CNN on the preprocessed volume.

    Until a trained checkpoint is wired up (via `set_model_weights(path)`),
    this returns a stub prediction marked `model_not_trained` with the
    caveats the UI must surface before any user sees it.
    """
    if _MODEL_WEIGHTS is None or not _MODEL_WEIGHTS.exists():
        return _stub_prediction(metadata)
    return _real_prediction(preprocessed, metadata)


def set_model_weights(path: Path, backbone: str = "monai_densenet") -> None:
    """Point the inference path at a trained checkpoint.

    `backbone` must match the architecture the checkpoint was saved from:
        - "monai_densenet" (the v0 fold*.pt set)
        - "med3d"          (the v1 fold*.pt set — 3D ResNet-50 topology)

    Invalidates the cached model if the path/backbone changes so the next
    request rebuilds.
    """
    global _MODEL_WEIGHTS, _MODEL_BACKBONE, _MODEL, _MODEL_DEVICE, _MODEL_CARD
    _MODEL_WEIGHTS = path
    _MODEL_BACKBONE = backbone
    _MODEL = None
    _MODEL_DEVICE = None
    _MODEL_CARD = {}
    logger.info("radiogenomics model weights set to %s (backbone=%s)", path, backbone)


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


def _build_backbone(backbone: str):
    """Build the same architecture used for training so the state_dict loads.

    Kept in-process here (not imported from hrd-radiogenomics) so drug-cell-viz
    has no build-time dependency on the research repo. The two definitions
    must stay in lockstep — the shared preprocessing contract (96^3 cube,
    HU window [-200, 250], [0, 1] normalised) means the tensors match, but
    the model topology also has to.
    """
    # Lazy-import — keeps the stub path light and avoids pulling torch/monai
    # into the dependency tree unless someone actually wires a checkpoint.
    from monai.networks.nets import DenseNet121, ResNet

    if backbone == "monai_densenet":
        return DenseNet121(
            spatial_dims=3,
            in_channels=1,
            out_channels=1,
            pretrained=False,  # PyTorch Hub has no 3D ImageNet; random-init.
        )
    if backbone == "med3d":
        return ResNet(
            block="bottleneck",
            layers=[3, 4, 6, 3],
            block_inplanes=[64, 128, 256, 512],
            spatial_dims=3,
            n_input_channels=1,
            num_classes=1,
        )
    raise RadiogenomicsError(f"unknown radiogenomics backbone: {backbone!r}")


def _load_or_get_model():
    """Lazy-load the model on first use, then cache it.

    Initial request takes ~2-4 s (torch import + architecture build + state
    load); subsequent requests reuse the cached module.
    """
    global _MODEL, _MODEL_DEVICE, _MODEL_CARD
    if _MODEL is not None:
        return _MODEL, _MODEL_DEVICE

    import torch

    assert _MODEL_WEIGHTS is not None
    ckpt = torch.load(_MODEL_WEIGHTS, map_location="cpu", weights_only=False)
    if "model_state" not in ckpt or "model_card" not in ckpt:
        raise RadiogenomicsError(
            "model checkpoint missing model_state / model_card keys; expected "
            "a checkpoint produced by the hrd-radiogenomics training pipeline"
        )
    # Prefer the backbone stored in the checkpoint's model_card so a v1 Med3D
    # file still loads even if RADIOGENOMICS_BACKBONE wasn't updated. Fall
    # back to the globally-configured backbone if the card doesn't record it.
    backbone = ckpt.get("model_card", {}).get("backbone", _MODEL_BACKBONE)
    model = _build_backbone(backbone)

    # The training repo wraps each backbone in an nn.Module for a clean
    # API (MonaiDenseNetClassifier.model.* and Med3DResNet50.backbone.*),
    # so the saved state_dict has a wrapper prefix on every key. Strip the
    # wrapper so the keys align with the bare DenseNet121 / ResNet we build
    # here. If neither prefix is present we fall through with the raw state.
    raw_state = ckpt["model_state"]
    for prefix in ("model.", "backbone."):
        if all(k.startswith(prefix) for k in raw_state.keys()):
            stripped = {k.removeprefix(prefix): v for k, v in raw_state.items()}
            logger.debug(
                "radiogenomics state: stripped %r prefix from %d keys",
                prefix, len(stripped),
            )
            raw_state = stripped
            break

    missing, unexpected = model.load_state_dict(raw_state, strict=False)
    if missing or unexpected:
        # Keep load non-strict so v0 and v1 heads can diverge slightly, but
        # complain loudly at WARN so a broken wire-up is visible at startup.
        logger.warning(
            "radiogenomics model load: %d missing / %d unexpected keys "
            "(backbone=%s)", len(missing), len(unexpected), backbone,
        )
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    _MODEL = model
    _MODEL_DEVICE = device
    _MODEL_CARD = dict(ckpt.get("model_card", {}))
    logger.info(
        "radiogenomics model loaded (backbone=%s, device=%s, val_auroc=%s, fold=%s)",
        backbone, device, _MODEL_CARD.get("val_auroc"), _MODEL_CARD.get("fold"),
    )
    return _MODEL, _MODEL_DEVICE


def _real_prediction(
    preprocessed: np.ndarray,
    metadata: VolumeMetadata,
) -> RadiogenomicsPrediction:
    """Run a forward pass and return a calibrated prediction.

    Inference pipeline:
        1. Reshape the preprocessed (Z, Y, X) array to (1, 1, 96, 96, 96).
        2. Forward pass on CPU/CUDA depending on host.
        3. sigmoid(logit) → HRD probability in [0, 1].
        4. Threshold at 0.5 for the binary label; confidence tier is a
           simple function of how far the probability sits from 0.5.
    """
    import torch

    model, device = _load_or_get_model()
    tensor = torch.from_numpy(preprocessed).float().unsqueeze(0).unsqueeze(0)  # (1,1,Z,Y,X)
    tensor = tensor.to(device)
    with torch.no_grad():
        logit = model(tensor)
        # MONAI DenseNet returns (B, num_classes=1); Med3D ResNet squeezes
        # similarly. Normalise to a single scalar regardless of shape.
        logit_scalar = float(logit.detach().cpu().view(-1)[0].item())
        probability = float(torch.sigmoid(torch.tensor(logit_scalar)).item())

    distance_from_boundary = abs(probability - 0.5)
    if distance_from_boundary < 0.10:
        confidence: Literal["low", "moderate", "high", "stub"] = "low"
    elif distance_from_boundary < 0.25:
        confidence = "moderate"
    else:
        confidence = "high"

    if probability >= 0.5:
        label: Literal[
            "predicted_hr_deficient",
            "predicted_hr_proficient",
            "uncertain",
            "model_not_trained",
        ] = "predicted_hr_deficient"
    else:
        label = "predicted_hr_proficient"
    if confidence == "low":
        label = "uncertain"

    # Cite the actual held-out AUROC of the loaded fold (dynamic so the
    # caveat tracks v0 vs v1 without a code change). Falls back to a generic
    # warning if the checkpoint was saved without model_card metrics.
    fold_auroc = _MODEL_CARD.get("val_auroc")
    backbone_name = _MODEL_CARD.get("backbone", _MODEL_BACKBONE)
    if fold_auroc is not None:
        perf_caveat = (
            f"Model trained on 135 TCGA-OV patients; this fold had held-out "
            f"validation AUROC {float(fold_auroc):.2f} ({backbone_name} backbone). "
            "Real-world accuracy on out-of-distribution scanners may be lower. "
            "Expect a drop of up to 0.15 AUROC across scanner manufacturers."
        )
    else:
        perf_caveat = (
            "Model trained on 135 TCGA-OV patients. Real-world accuracy on "
            "out-of-distribution scanners may be lower. Expect a drop of up "
            "to 0.15 AUROC across scanner manufacturers."
        )

    return RadiogenomicsPrediction(
        metadata=metadata,
        hrd_probability=probability,
        label=label,
        confidence=confidence,
        caveats=[
            "Research prototype. Not FDA-cleared, not a medical device.",
            perf_caveat,
            "This prediction alone is not sufficient for a clinical decision. "
            "Definitive HRD status still requires tumor sequencing (Myriad "
            "myChoice, FoundationOne CDx, or equivalent CLIA-certified assay).",
            "Do not use for any clinical decision without oncologist review.",
        ],
    )
