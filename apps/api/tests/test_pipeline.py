"""End-to-end smoke test for the Snakemake variant-report pipeline.

Runs the full VCF → normalize → filter → classify → report workflow against
the bundled synthetic fixture and asserts that the resulting `report.json`
contains the expected catalog matches and PGx verdicts.

Skipped if snakemake isn't installed (it's an optional dependency via the
`pipeline` extra). In CI we install with `--extra pipeline` so this runs.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = REPO_ROOT / "pipelines"


def _snakemake_available() -> bool:
    return shutil.which("snakemake") is not None


@pytest.mark.skipif(not _snakemake_available(), reason="snakemake not installed")
def test_pipeline_runs_end_to_end_against_fixture(tmp_path) -> None:
    """Fresh snakemake run against the fixture should produce a clean report."""
    results_dir = tmp_path / "results"
    # Point snakemake at an isolated results directory so we don't clobber
    # anything the developer has lying around.
    override = tmp_path / "config.yaml"
    override.write_text(
        "results_dir: "
        + str(results_dir)
        + "\n"
        + "default_drug: tamoxifen\n"
        + "samples:\n"
        + "  test_sample:\n"
        + "    vcf: apps/api/tests/fixtures/test_sample.vcf\n"
        + "    drug_id: tamoxifen\n"
    )

    result = subprocess.run(
        [
            "snakemake",
            "--snakefile",
            str(PIPELINE_DIR / "Snakefile"),
            "--configfile",
            str(override),
            "--cores",
            "1",
            "--directory",
            str(REPO_ROOT),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"snakemake failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    report_path = results_dir / "test_sample" / "report.json"
    assert report_path.exists(), f"missing report.json; stderr: {result.stderr}"
    report = json.loads(report_path.read_text())

    # Five PASS records, five catalog detections.
    detection_ids = {d["catalog_id"] for d in report["detections"]}
    assert detection_ids == {
        "DPYD_c2846A_T",
        "DPYD_star2A",
        "TPMT_star2",
        "BRCA1_C61G",
        "CYP2D6_star4",
    }

    # CPIC rule for homozygous CYP2D6*4 should have fired.
    assert report["analysis"] is not None
    phenotypes = {v["phenotype"].lower() for v in report["analysis"]["pgx_verdicts"]}
    assert any("poor metabolizer" in p for p in phenotypes), report["analysis"][
        "pgx_verdicts"
    ]

    # Human-readable report rendered alongside.
    txt_path = results_dir / "test_sample" / "report.txt"
    assert txt_path.exists()
    assert "CYP2D6*4" in txt_path.read_text()
