"""Generate sample_data/luna_pathology.pdf for the demo.

Run: .venv/bin/python scripts/generate_luna_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors


OUT = Path(__file__).resolve().parents[1] / "sample_data" / "luna_pathology.pdf"


def build() -> None:
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    body.fontSize = 10
    body.leading = 14
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, spaceAfter=8, textColor=colors.HexColor("#003366"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceAfter=4, textColor=colors.HexColor("#003366"))
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.grey)

    story = []

    story.append(Paragraph("ONTARIO VETERINARY DIAGNOSTIC LABORATORY", h1))
    story.append(Paragraph("Surgical Pathology Report — Confidential", h2))
    story.append(Paragraph(
        "50 Stone Road East, Guelph ON N1G 2W1 &nbsp;&nbsp;|&nbsp;&nbsp; Tel: (519) 824-4120 &nbsp;&nbsp;|&nbsp;&nbsp; Fax: (519) 824-5930",
        small,
    ))
    story.append(Spacer(1, 0.2 * inch))

    # Patient info table
    patient_data = [
        ["Patient Name:", "Luna", "Accession #:", "OVDL-2026-04710"],
        ["Species:", "Canine (Canis familiaris)", "Date of Biopsy:", "April 10, 2026"],
        ["Breed:", "Golden Retriever", "Date of Report:", "April 14, 2026"],
        ["Age:", "8 years", "Referring Vet:", "Dr. Sarah Chen, DVM"],
        ["Weight:", "32.4 kg", "Clinic:", "Bloor West Animal Hospital"],
        ["Sex:", "FS (spayed female)", "Owner Location:", "Toronto, ON, Canada"],
    ]
    t = Table(patient_data, colWidths=[1.2 * inch, 2.2 * inch, 1.2 * inch, 2.0 * inch])
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONT", (2, 0), (2, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f6fa")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("CLINICAL HISTORY", h2))
    story.append(Paragraph(
        "Luna presented 6 months ago with a firm, ulcerated mass on the left hind leg, proximal to the tarsal joint. "
        "Fine-needle aspiration suggested mast cell neoplasia. The mass was surgically excised on November 12, 2025, "
        "with histopathology confirming Patnaik Grade II (Kiupel high-grade) cutaneous mast cell tumor. Surgical "
        "margins were narrow (1 mm on deep margin). Adjuvant vinblastine/prednisone chemotherapy (8 cycles) was "
        "completed in February 2026.",
        body,
    ))
    story.append(Paragraph(
        "Patient was tumor-free for approximately 8 weeks following chemotherapy completion. On March 28, 2026, a new "
        "2.4 cm firm nodule was palpated at the surgical site. Ultrasound showed no regional lymphadenopathy, and "
        "thoracic radiographs were clear. Excisional biopsy was performed on April 10, 2026 — this report.",
        body,
    ))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("GROSS DESCRIPTION", h2))
    story.append(Paragraph(
        "Received in formalin: a single firm, tan-white, well-circumscribed mass measuring 2.4 × 2.1 × 1.8 cm. "
        "Cut surface is homogeneous with focal areas of hemorrhage. Submitted in toto.",
        body,
    ))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("MICROSCOPIC DESCRIPTION", h2))
    story.append(Paragraph(
        "Dermis and subcutis contain a densely cellular, poorly circumscribed infiltrative neoplasm composed of sheets "
        "of round cells. Cells exhibit marked anisocytosis and anisokaryosis, with abundant pale-staining cytoplasm "
        "containing moderate to numerous metachromatic granules (toluidine blue positive). Mitotic index: 8 per 10 HPF. "
        "Multinucleated cells are present (2-3 per 10 HPF). Deep margin appears infiltrated.",
        body,
    ))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("MOLECULAR / GENOMIC FINDINGS", h2))
    story.append(Paragraph(
        "Tumor DNA was extracted and submitted for whole-exome sequencing (WES) and RNA-seq at the University of Guelph "
        "Genomics Facility. Somatic variant calling identified 847 non-synonymous mutations; 23 in protein-coding "
        "oncogenes. Of particular note: KIT exon 11 (V559G, V560D) and exon 17 (D816V) mutations consistent with "
        "canine mast cell tumor driver biology; BRAF V600E; and TP53 R175H/R248Q/R273H hotspot mutations. Full variant "
        "call format file attached (luna_tumor.vcf).",
        body,
    ))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("DLA TYPING", h2))
    story.append(Paragraph(
        "DLA class I typing performed at UC Davis VGL. Patient genotype: DLA-88*50101 / DLA-88*00801. Heterozygous.",
        body,
    ))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("DIAGNOSIS", h2))
    story.append(Paragraph(
        "<b>Cutaneous mast cell tumor, Patnaik Grade III (Kiupel high-grade), left hind leg, local recurrence.</b> "
        "Deep margin infiltration noted. KIT activating mutations present in both juxtamembrane (exon 11) and "
        "kinase (exon 17) domains — predicts poor response to toceranib (Palladia) and suggests aggressive biologic "
        "behavior.",
        body,
    ))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("PRIOR TREATMENTS", h2))
    story.append(Paragraph(
        "Wide local excision (Nov 2025, narrow margins); Vinblastine/Prednisone chemotherapy, 8 cycles (Dec 2025 - Feb 2026).",
        body,
    ))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("RECOMMENDATIONS", h2))
    story.append(Paragraph(
        "Given the local recurrence despite prior wide excision and chemotherapy, plus the presence of both exon 11 "
        "and exon 17 KIT mutations (which confer toceranib resistance), the owner has inquired about experimental "
        "immunotherapy options. The high somatic mutation burden (847 mutations) suggests a potentially favorable "
        "neoantigen vaccine target profile. Referral to a board-certified veterinary oncologist with immunotherapy "
        "experience is recommended. Consider enrollment in comparative oncology trials if available.",
        body,
    ))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph(
        "Electronically signed by Dr. Rebecca Morales, DVM, DACVP — Board-certified Veterinary Pathologist",
        small,
    ))
    story.append(Paragraph("Ontario Veterinary Diagnostic Laboratory, 04/14/2026 16:22 EDT", small))

    doc.build(story)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
