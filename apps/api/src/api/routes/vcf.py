"""VCF upload + analysis endpoint."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from api.models import AnalysisResult, VariantInput
from api.services import analysis as analysis_service
from api.services import vcf as vcf_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vcf", tags=["vcf"])


class VcfDetectionDTO(BaseModel):
    catalog_id: str
    gene: str
    display_name: str
    chrom: str
    pos: int
    ref: str
    alt: str
    zygosity: str
    sample: str
    vcf_filter: str


class VcfAnalyzeResponse(BaseModel):
    total_records: int
    records_pass: int
    samples: list[str]
    analyzed_sample: str
    detections: list[VcfDetectionDTO]
    novel_brca1_missense: list[str]
    analysis: AnalysisResult | None


@router.post("/analyze", response_model=VcfAnalyzeResponse)
async def analyze_vcf(
    file: UploadFile = File(...),
    drug_id: str = "tamoxifen",
    sample: str | None = None,
) -> VcfAnalyzeResponse:
    """Parse an uploaded VCF, detect catalog variants, run the drug analysis.

    Accepts plain .vcf or bgzipped .vcf.gz (cyvcf2 handles both). Streams the
    file to a tempfile because cyvcf2 needs a filesystem path (to lean on
    htslib's memory-mapped reader) rather than a file-like object.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="no filename on upload")
    suffix = ".vcf.gz" if file.filename.endswith(".gz") else ".vcf"

    # Stream into a tempfile. NamedTemporaryFile + delete=False because cyvcf2
    # may still hold handles during the parse; we clean up in `finally`.
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    try:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 MiB chunks
            if not chunk:
                break
            tmp.write(chunk)
        tmp.close()

        try:
            result = vcf_service.ingest(tmp_path, sample=sample)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("VCF parse failed")
            raise HTTPException(
                status_code=400,
                detail=f"could not parse VCF: {exc}",
            ) from exc

        # Run the existing pharmacogenomic analysis against the detected variants.
        variants: list[VariantInput] = vcf_service.detections_to_variant_inputs(
            result.detections,
        )
        analysis: AnalysisResult | None = None
        if variants:
            try:
                analysis = await analysis_service.run_analysis(drug_id, variants)
            except analysis_service.AnalysisError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        return VcfAnalyzeResponse(
            total_records=result.total_records,
            records_pass=result.records_pass,
            samples=result.samples,
            analyzed_sample=result.analyzed_sample,
            detections=[VcfDetectionDTO(**d.__dict__) for d in result.detections],
            novel_brca1_missense=result.novel_brca1_missense,
            analysis=analysis,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
