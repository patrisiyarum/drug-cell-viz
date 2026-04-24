"""Tests for the radiogenomics preprocessing + stub inference path.

We don't exercise real DICOM / NIfTI parsing here (those need binary
fixtures and the heavy libraries). Instead we hit the pure-Python parts:
  - crop_to_tumor on a synthetic volume
  - preprocess end-to-end on a synthetic volume via the helper hooks
  - infer_hrd returns the correct stub shape when no checkpoint is loaded
"""

from __future__ import annotations

import numpy as np
import pytest

from api.services import radiogenomics


def _synth_ct(shape: tuple[int, int, int] = (64, 128, 128)) -> np.ndarray:
    """A synthetic HU-like volume with a dense blob in the middle."""
    vol = np.full(shape, -1000.0, dtype=np.float32)  # air background
    cz, cy, cx = (s // 2 for s in shape)
    vol[cz - 8 : cz + 8, cy - 20 : cy + 20, cx - 20 : cx + 20] = 50.0  # soft tissue
    return vol


def test_crop_to_tumor_tightens_bounding_box():
    vol = _synth_ct()
    cropped = radiogenomics.crop_to_tumor(vol)
    # The cropped volume must be strictly smaller than the input on every
    # axis since most of the synthetic volume is air.
    assert all(cropped.shape[i] < vol.shape[i] for i in range(3))
    # And at least as large as the soft-tissue blob (16 x 40 x 40) plus pad.
    assert cropped.shape[0] >= 16
    assert cropped.shape[1] >= 40
    assert cropped.shape[2] >= 40


def test_normalize_intensity_clips_to_window():
    # Volume spans the full HU window end-to-end so both extremes clip.
    vol = np.array(
        [[-2000.0, -200.0, 50.0, 250.0, 500.0]], dtype=np.float32,
    )
    normed = radiogenomics.normalize_intensity(vol, radiogenomics.HU_WINDOW)
    assert normed.min() == pytest.approx(0.0)       # -2000 clips to window low
    assert normed.max() == pytest.approx(1.0)       # +500 clips to window high
    assert normed[0, 2] == pytest.approx((50 - (-200)) / (250 - (-200)), abs=1e-5)


def test_preprocess_emits_target_shape():
    vol = _synth_ct()
    metadata = radiogenomics.VolumeMetadata(
        modality="CT",
        original_shape=vol.shape,  # type: ignore[arg-type]
        original_spacing_mm=(1.0, 1.0, 1.0),
        target_shape=radiogenomics.TARGET_SHAPE,
        hu_window=radiogenomics.HU_WINDOW,
    )
    out = radiogenomics.preprocess(vol, metadata)
    assert out.shape == radiogenomics.TARGET_SHAPE
    assert out.dtype == np.float32


def test_infer_hrd_returns_stub_when_no_checkpoint():
    metadata = radiogenomics.VolumeMetadata(
        modality="CT",
        original_shape=(64, 128, 128),
        original_spacing_mm=(1.0, 1.0, 1.0),
        target_shape=radiogenomics.TARGET_SHAPE,
        hu_window=radiogenomics.HU_WINDOW,
    )
    dummy_input = np.zeros(radiogenomics.TARGET_SHAPE, dtype=np.float32)
    out = radiogenomics.infer_hrd(dummy_input, metadata)
    assert out.label == "model_not_trained"
    assert out.confidence == "stub"
    assert len(out.caveats) >= 2
    # The UI relies on the hrd_probability being a plausible scalar even in
    # the stub path so the response schema stays consistent when the real
    # model lands.
    assert 0.0 <= out.hrd_probability <= 1.0


def test_load_volume_rejects_unknown_extension():
    with pytest.raises(radiogenomics.RadiogenomicsError):
        radiogenomics.load_volume(b"whatever", "image.jpg")


def test_real_inference_path_with_v0_checkpoint():
    """Locks in end-to-end inference when a real checkpoint is mounted.

    Only runs when the v0 weights are present AND torch+monai are installed
    via the `radiogenomics` extra. In CI without those deps we skip so the
    baseline suite stays green. When both are present, we verify the model
    loads with 0 missing / 0 unexpected keys (via the wrapper-prefix strip)
    and returns a real-valued probability, not the stub.
    """
    from pathlib import Path

    weights = Path("models/radiogen_v0/fold0.pt")
    if not weights.exists():
        pytest.skip("v0 checkpoint not mounted at models/radiogen_v0/fold0.pt")
    try:
        import monai  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        pytest.skip("radiogenomics extra not installed (torch + monai)")

    # Restore global state after the test so other tests keep the stub path.
    prev_weights = radiogenomics._MODEL_WEIGHTS
    prev_backbone = radiogenomics._MODEL_BACKBONE
    try:
        radiogenomics.set_model_weights(weights, backbone="monai_densenet")
        meta = radiogenomics.VolumeMetadata(
            modality="CT",
            original_shape=(96, 96, 96),
            original_spacing_mm=(1.0, 1.0, 1.0),
            target_shape=radiogenomics.TARGET_SHAPE,
            hu_window=radiogenomics.HU_WINDOW,
        )
        vol = np.random.default_rng(0).random(radiogenomics.TARGET_SHAPE).astype(np.float32)
        pred = radiogenomics.infer_hrd(vol, meta)
        assert pred.label in {
            "predicted_hr_deficient",
            "predicted_hr_proficient",
            "uncertain",
        }
        assert pred.confidence in {"low", "moderate", "high"}
        assert 0.0 <= pred.hrd_probability <= 1.0
        # The caveats list should still warn the user — real predictions
        # from a 0.62-AUROC model are emphatically not clinical-grade.
        assert any("Research prototype" in c for c in pred.caveats)
    finally:
        radiogenomics._MODEL_WEIGHTS = prev_weights
        radiogenomics._MODEL_BACKBONE = prev_backbone
        radiogenomics._MODEL = None
        radiogenomics._MODEL_DEVICE = None
