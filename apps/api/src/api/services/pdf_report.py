"""Doctor-visit PDF report generator.

Given an AnalysisResult, produce a single-file PDF with everything a patient
would want to walk into an oncology appointment prepared:
  - cover: drug + tumor subtype + date
  - HRD composite result (headline and evidence)
  - current-drug assessment (is it right for you?)
  - detected variants
  - pharmacogenomic verdicts (CPIC / FDA)
  - questions to ask the doctor
  - how we know this (sources)
  - disclaimers

Uses reportlab's Platypus (high-level flow-based layout) so styling stays
simple and the doc reflows cleanly regardless of content length.

No images, no 3D renders — keeps the document printable on any B&W office
printer and accessible. The accompanying web UI shows the 3D view; the PDF
is the "take this to the appointment" artifact.
"""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from api.models import AnalysisResult


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Heading1"],
            fontSize=20,
            leading=24,
            spaceAfter=12,
            textColor=colors.HexColor("#0f172a"),
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontSize=14,
            leading=18,
            spaceBefore=14,
            spaceAfter=6,
            textColor=colors.HexColor("#0f172a"),
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontSize=11,
            leading=14,
            spaceBefore=8,
            spaceAfter=3,
            textColor=colors.HexColor("#334155"),
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontSize=10,
            leading=14,
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["BodyText"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748b"),
        ),
        "callout": ParagraphStyle(
            "callout",
            parent=base["BodyText"],
            fontSize=11,
            leading=15,
            spaceBefore=8,
            spaceAfter=8,
            leftIndent=8,
            borderPadding=8,
            borderWidth=1,
            borderColor=colors.HexColor("#cbd5e1"),
            backColor=colors.HexColor("#f8fafc"),
        ),
    }


def _p(text: str, style) -> Paragraph:
    # reportlab's Paragraph supports a tiny HTML subset; we escape angle brackets
    # to avoid accidentally breaking on variant strings like "p.Cys61Gly>..."
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe, style)


def build_pdf(result: AnalysisResult, patient_label: str | None = None) -> bytes:
    """Render the full report to a PDF bytestring."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        title=f"Pharmacogenomic report — {result.drug_name}",
        author="drug-cell-viz",
        subject="Doctor-visit report",
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    S = _styles()
    flow = []

    # --- Cover ---
    flow.append(_p("Pharmacogenomic report", S["title"]))
    flow.append(
        _p(
            f"For discussion with your oncologist · {datetime.utcnow().strftime('%B %-d, %Y')}",
            S["meta"],
        )
    )
    flow.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1")))
    flow.append(Spacer(1, 8))
    flow.append(_p(f"Drug: <b>{result.drug_name}</b>", S["body"]))
    flow.append(_p(f"Target protein: <b>{result.target_gene}</b> ({result.target_uniprot})", S["body"]))
    if patient_label:
        flow.append(_p(f"Patient: <b>{patient_label}</b>", S["body"]))
    flow.append(Spacer(1, 8))
    flow.append(_p(result.headline, S["callout"]))

    # --- HRD composite ---
    if result.hrd:
        flow.append(_p("Homologous-recombination deficiency (HRD)", S["h2"]))
        label_pretty = {
            "hr_deficient": "HR-deficient",
            "hr_proficient": "HR-proficient",
            "indeterminate": "Indeterminate",
        }[result.hrd.label]
        flow.append(_p(f"<b>Result:</b> {label_pretty} (score {result.hrd.score}/100)", S["body"]))
        flow.append(_p(result.hrd.summary, S["body"]))
        flow.append(_p("PARP-inhibitor context", S["h3"]))
        flow.append(_p(result.hrd.parp_inhibitor_context, S["body"]))
        if result.hrd.evidence:
            flow.append(_p("Evidence", S["h3"]))
            rows = [["Gene", "Variant", "Source", "Detail"]]
            for e in result.hrd.evidence:
                rows.append([e.gene, e.variant_label, e.source.replace("_", " "), e.detail])
            t = Table(rows, colWidths=[0.7 * inch, 1.7 * inch, 1.2 * inch, 3.2 * inch])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                        ("WORDWRAP", (3, 0), (3, -1), "CJK"),
                    ]
                )
            )
            flow.append(t)

    # --- Current-drug assessment ---
    if result.current_drug_assessment:
        cda = result.current_drug_assessment
        flow.append(_p("Is this drug the right match for you?", S["h2"]))
        verdict_pretty = {
            "well_matched": "Well matched",
            "acceptable": "Acceptable",
            "review_needed": "Review needed",
            "unknown": "Not enough data",
        }[cda.verdict]
        flow.append(_p(f"<b>Verdict:</b> {verdict_pretty}", S["body"]))
        flow.append(_p(cda.headline, S["callout"]))
        flow.append(_p(cda.rationale, S["body"]))
        if cda.better_options:
            flow.append(_p("Drugs worth asking about", S["h3"]))
            for s in cda.better_options:
                flow.append(_p(f"<b>{s.name}</b> — {s.reason}", S["body"]))

    # --- Pharmacogenomic verdicts ---
    if result.pgx_verdicts:
        flow.append(_p("Pharmacogenomic guidance (CPIC / FDA)", S["h2"]))
        for v in result.pgx_verdicts:
            flow.append(
                _p(
                    f"<b>[Evidence {v.evidence_level}] {v.drug_name} × {v.variant_label}</b> "
                    f"({v.zygosity})",
                    S["h3"],
                )
            )
            flow.append(_p(f"Phenotype: {v.phenotype}", S["body"]))
            flow.append(_p(v.recommendation, S["body"]))
            flow.append(_p(f"Source: {v.source}", S["meta"]))

    # --- Questions for the doctor ---
    if result.plain_language.questions_to_ask:
        flow.append(_p("Questions to ask your doctor", S["h2"]))
        for i, q in enumerate(result.plain_language.questions_to_ask, 1):
            flow.append(_p(f"{i}. {q}", S["body"]))

    # --- Plain-language summary ---
    pl = result.plain_language
    flow.append(_p("What this means", S["h2"]))
    flow.append(_p("What you'd see in the 3D view", S["h3"]))
    flow.append(_p(pl.what_you_see, S["body"]))
    flow.append(_p("How this drug works", S["h3"]))
    flow.append(_p(pl.how_the_drug_works, S["body"]))
    flow.append(_p("What this means for you", S["h3"]))
    flow.append(_p(pl.what_it_means_for_you, S["body"]))
    flow.append(_p("Next steps", S["h3"]))
    flow.append(_p(pl.next_steps, S["body"]))

    # --- How we know this ---
    hw = pl.how_we_know
    flow.append(_p("How we know this", S["h2"]))
    flow.append(_p(f"<b>{hw.source}</b>", S["body"]))
    flow.append(_p(hw.summary, S["body"]))
    if hw.link:
        flow.append(_p(f"Reference: {hw.link}", S["meta"]))

    # --- Disclaimers ---
    flow.append(PageBreak())
    flow.append(_p("Important — read this", S["h2"]))
    for d in result.disclaimers:
        flow.append(_p("• " + d, S["body"]))
    if result.hrd:
        for c in result.hrd.caveats:
            flow.append(_p("• " + c, S["body"]))

    # --- Glossary ---
    if pl.glossary:
        flow.append(_p("Glossary", S["h2"]))
        for g in pl.glossary:
            flow.append(_p(f"<b>{g.term}</b> — {g.definition}", S["body"]))

    doc.build(flow)
    return buf.getvalue()
