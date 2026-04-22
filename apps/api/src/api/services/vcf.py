"""VCF ingestion for clinical-grade sequencing data.

Wraps cyvcf2 (htslib) to parse (b)gzipped VCFs, filter to variants we
recognize in the catalog, and convert each hit into the same `VariantInput`
shape the rest of the analysis pipeline already consumes. Works for single-
and multi-sample VCFs; for multi-sample files we use the first sample unless
a specific sample name is provided.

Design choice: v0 matches variants by exact (chrom, pos, ref, alt) lookup
against a hand-curated hg38 coordinate map. That's narrow on purpose; real
clinical pipelines run a full VEP/annovar pass first. Emitting the rsID and
coordinate provenance on every hit makes it easy to extend with a real
variant-annotation step (ClinVar, gnomAD) later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from cyvcf2 import VCF, Variant

from api.models import VariantInput

logger = logging.getLogger(__name__)

Zygosity = Literal["heterozygous", "homozygous"]


@dataclass(frozen=True)
class CatalogCoordinate:
    """One catalog variant addressed by its hg38 genomic coordinate.

    VCF files ship coords on whichever genome build the lab used; we
    normalize 'chr' prefix at lookup time.
    """

    catalog_id: str
    gene: str
    chrom: str        # no 'chr' prefix
    pos: int          # 1-indexed VCF position
    ref: str
    alt: str
    display_name: str


# Hg38 coordinates for the catalog variants we can match from a VCF.
# Sources: dbSNP (rsID → position), ClinVar (for indels), LRG/RefSeq for BRCA.
# UGT1A1*28 is a TA-repeat indel that SNV-only callers miss — excluded here.
_COORDS: list[CatalogCoordinate] = [
    # CYP2D6*4 — rs3892097. Note: the FORWARD-strand alt is "A"; CYP2D6 sits
    # on the minus strand, so some VCFs report "T" depending on the pipeline.
    CatalogCoordinate(
        catalog_id="CYP2D6_star4",
        gene="CYP2D6",
        chrom="22",
        pos=42128945,
        ref="C",
        alt="T",
        display_name="CYP2D6*4 (rs3892097)",
    ),
    # DPYD*2A — rs3918290.
    CatalogCoordinate(
        catalog_id="DPYD_star2A",
        gene="DPYD",
        chrom="1",
        pos=97573863,
        ref="T",
        alt="C",   # forward-strand representation (some pipelines flip)
        display_name="DPYD*2A (rs3918290)",
    ),
    # DPYD c.2846A>T — rs67376798.
    CatalogCoordinate(
        catalog_id="DPYD_c2846A_T",
        gene="DPYD",
        chrom="1",
        pos=97450058,
        ref="A",
        alt="T",
        display_name="DPYD c.2846A>T (rs67376798)",
    ),
    # TPMT*3A — this allele is the combination of rs1800460 + rs1142345.
    # We register both SNVs; caller-side we merge when both appear.
    CatalogCoordinate(
        catalog_id="TPMT_star3A",
        gene="TPMT",
        chrom="6",
        pos=18139228,
        ref="C",
        alt="T",
        display_name="TPMT*3A marker (rs1800460)",
    ),
    CatalogCoordinate(
        catalog_id="TPMT_star3A",
        gene="TPMT",
        chrom="6",
        pos=18130918,
        ref="T",
        alt="C",
        display_name="TPMT*3A marker (rs1142345)",
    ),
    # TPMT*2 — rs1800462.
    CatalogCoordinate(
        catalog_id="TPMT_star2",
        gene="TPMT",
        chrom="6",
        pos=18143955,
        ref="G",
        alt="C",
        display_name="TPMT*2 (rs1800462)",
    ),
    # BRCA1 p.Cys61Gly — chr17:43124097 A>C (hg38, minus strand → BRCA1 cDNA T→G).
    CatalogCoordinate(
        catalog_id="BRCA1_C61G",
        gene="BRCA1",
        chrom="17",
        pos=43124097,
        ref="A",
        alt="C",
        display_name="BRCA1 p.Cys61Gly (c.181T>G)",
    ),
]


def _normalize_chrom(c: str) -> str:
    return c[3:] if c.startswith("chr") else c


@dataclass(frozen=True)
class VcfDetection:
    """A single VCF record matched to a catalog entry."""

    catalog_id: str
    gene: str
    display_name: str
    chrom: str
    pos: int
    ref: str
    alt: str
    zygosity: Zygosity
    sample: str
    vcf_filter: str   # PASS / LowQual / etc


@dataclass(frozen=True)
class VcfIngestionResult:
    """Summary returned to the frontend after parsing an uploaded VCF."""

    total_records: int
    records_pass: int
    samples: list[str]
    analyzed_sample: str
    detections: list[VcfDetection]
    novel_brca1_missense: list[str]   # HGVS-protein strings for the BRCA1 classifier
    note: str | None = None


def _zygosity_from_gt(gt_types: Iterable[int]) -> Zygosity | None:
    """Translate cyvcf2 genotype codes (0=HOM_REF, 1=HET, 2=UNKNOWN, 3=HOM_ALT)."""
    for code in gt_types:
        if code == 1:
            return "heterozygous"
        if code == 3:
            return "homozygous"
    return None


def ingest(path: Path, sample: str | None = None) -> VcfIngestionResult:
    """Parse a VCF file and return all catalog matches for the chosen sample.

    If `sample` is None the first sample in the VCF is analyzed.
    """
    # Index coords by (chrom, pos) for O(1) lookup while we scan records.
    coord_index: dict[tuple[str, int], list[CatalogCoordinate]] = {}
    for c in _COORDS:
        coord_index.setdefault((c.chrom, c.pos), []).append(c)

    vcf = VCF(str(path))
    samples: list[str] = list(vcf.samples) or ["<single-sample>"]
    analyzed = sample or samples[0]
    if sample and sample not in samples:
        raise ValueError(
            f"sample {sample!r} not in VCF; available samples: {samples}"
        )
    sample_idx = samples.index(analyzed) if samples != ["<single-sample>"] else 0

    detections: list[VcfDetection] = []
    novel_brca1: list[str] = []
    total = 0
    pass_count = 0

    for rec in vcf:
        total += 1
        filt = rec.FILTER or "PASS"
        if filt == "PASS":
            pass_count += 1

        chrom = _normalize_chrom(rec.CHROM)
        bucket = coord_index.get((chrom, rec.POS))

        if bucket:
            for coord in bucket:
                for alt in rec.ALT:
                    if rec.REF == coord.ref and alt == coord.alt:
                        zyg = _sample_zygosity(rec, sample_idx)
                        if zyg is None:
                            continue
                        detections.append(
                            VcfDetection(
                                catalog_id=coord.catalog_id,
                                gene=coord.gene,
                                display_name=coord.display_name,
                                chrom=chrom,
                                pos=rec.POS,
                                ref=rec.REF,
                                alt=alt,
                                zygosity=zyg,
                                sample=analyzed,
                                vcf_filter=filt,
                            )
                        )

        # Opportunistic: scan for BRCA1 missense variants outside the curated
        # catalog so they can feed the ML classifier. We only do this when
        # VEP has already annotated the record via the CSQ INFO field (a
        # proper clinical pipeline runs VEP before this stage).
        csq = rec.INFO.get("CSQ")
        if csq and chrom == "17":
            hgvs = _extract_brca1_hgvsp(csq)
            if hgvs is not None:
                novel_brca1.append(hgvs)

    vcf.close()

    return VcfIngestionResult(
        total_records=total,
        records_pass=pass_count,
        samples=samples,
        analyzed_sample=analyzed,
        detections=detections,
        novel_brca1_missense=list(dict.fromkeys(novel_brca1)),  # dedupe, keep order
    )


def _sample_zygosity(rec: Variant, sample_idx: int) -> Zygosity | None:
    """Return the sample's zygosity for this record, or None if missing/ref.

    cyvcf2.Variant.gt_types is a numpy array of codes per sample:
        0 HOM_REF   1 HET   2 UNKNOWN   3 HOM_ALT
    """
    try:
        gt_types = rec.gt_types
    except Exception:
        return None
    if len(gt_types) <= sample_idx:
        return None
    code = int(gt_types[sample_idx])
    if code == 1:
        return "heterozygous"
    if code == 3:
        return "homozygous"
    return None  # HOM_REF or UNKNOWN — treat as absent


def _extract_brca1_hgvsp(csq: str | bytes) -> str | None:
    """Pull an HGVSp (protein-level) substitution from a VEP CSQ annotation.

    VEP CSQ is a pipe-delimited string. The default VEP config includes an
    HGVSp field; real clinical pipelines run VEP with --hgvs. We look for
    anything of the form `...:p.X###Y` where the gene is BRCA1.
    """
    s = csq.decode() if isinstance(csq, bytes) else csq
    for entry in s.split(","):
        parts = entry.split("|")
        if not any("BRCA1" in p for p in parts):
            continue
        for p in parts:
            # VEP emits HGVSp like "ENSP00000350283.3:p.Cys61Gly"
            if ":p." in p:
                prot = p.split(":p.", 1)[1]
                if prot and not prot.startswith("="):
                    return f"p.{prot}"
    return None


def detections_to_variant_inputs(ds: list[VcfDetection]) -> list[VariantInput]:
    """Collapse detections into the `VariantInput` list the analysis API wants.

    Same merge behavior as the 23andMe parser: if two markers map to the
    same catalog_id (e.g. TPMT*3A's two SNVs), keep the most-severe zygosity.
    """
    by_id: dict[str, Zygosity] = {}
    for d in ds:
        prev = by_id.get(d.catalog_id)
        if prev is None or (prev == "heterozygous" and d.zygosity == "homozygous"):
            by_id[d.catalog_id] = d.zygosity
    return [
        VariantInput(catalog_id=cid, zygosity=zyg)
        for cid, zyg in by_id.items()
    ]


def count_supported_coordinates() -> int:
    """Number of catalog variants addressable by exact (chrom, pos, ref, alt)."""
    return len({c.catalog_id for c in _COORDS})
