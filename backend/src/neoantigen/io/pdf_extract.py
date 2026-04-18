"""Per-PDF extraction — text + per-page MediX VLM vision findings.

Single entrypoint: ``extract_document(filename, pdf_bytes) -> DocumentExtraction``.

For each page:
  1. pypdf text extraction (best-effort).
  2. Rasterize the page to JPEG.
  3. Hand the page image to MediX (Qwen3-VL-based, GH200 vLLM tunnel) asking
     for any oncology-relevant findings on that page, structured as a
     ``PageFinding``.

Every call is best-effort — missing deps / offline tunnels degrade to empty
findings rather than raising.
"""

from __future__ import annotations

import asyncio
import io
import re

from pydantic import BaseModel, Field

from ..agent._llm import call_with_vision, has_medix_key
from ..agent.events import EventKind, emit
from ..models import DocumentExtraction, Mutation, PageFinding


MAX_PAGES = 20          # Hard cap per PDF to keep per-case latency bounded.
RASTER_DPI = 150
VISION_MAX_TOKENS = 1200
VISION_CONCURRENCY = 3  # Run up to N pages concurrently against the VLM.


# ─────────────────────────────────────────────────────────────
# Per-page VLM schema
# ─────────────────────────────────────────────────────────────


class _VisionPayload(BaseModel):
    """Loose schema the VLM fills in per page. Everything is optional."""

    page_description: str = Field(
        default="",
        description="One sentence describing what this page shows (report header, IHC panel, imaging figure, text-only, etc.)",
    )
    primary_cancer_type: str | None = Field(
        default=None,
        description=(
            "Snake_case cancer type when stated, e.g. cutaneous_melanoma, "
            "lung_adenocarcinoma, lung_squamous, breast_ductal_carcinoma, "
            "colorectal_adenocarcinoma, gastric_carcinoma, pancreatic_carcinoma, "
            "prostate_carcinoma, ovarian_carcinoma, renal_cell_carcinoma, "
            "hepatocellular_carcinoma, bladder_carcinoma, head_neck_scc, "
            "glioblastoma, lymphoma_dlbcl, multiple_myeloma, other."
        ),
    )
    histology: str | None = Field(
        default=None,
        description="Free-text histology as stated, e.g. 'adenocarcinoma', 'nodular melanoma', 'ductal carcinoma in situ'.",
    )
    primary_site: str | None = Field(
        default=None,
        description="Free-text primary tumor site as stated, e.g. 'right upper lobe lung', 'left breast', 'sigmoid colon'.",
    )
    melanoma_subtype: str | None = None
    breslow_thickness_mm: float | None = None
    ulceration: bool | None = None
    mitotic_rate_per_mm2: float | None = None
    tils_present: str | None = None
    pdl1_estimate: str | None = None
    lag3_ihc_percent: float | None = None
    ajcc_stage: str | None = None
    age_years: int | None = None
    ecog: int | None = None
    measurable_disease_recist: bool | None = None
    life_expectancy_months: int | None = None
    prior_systemic_therapy: bool | None = None
    prior_anti_pd1: bool | None = None
    mutations_text: list[str] = Field(
        default_factory=list,
        description="Raw strings of any gene mutations spotted on this page, e.g. 'BRAF V600E', 'NRAS Q61R'",
    )
    relevant_notes: str = ""


VISION_SYSTEM_PROMPT = """You are an oncology data extractor reading one page of
a patient's medical document (pathology report, IHC addendum, NGS report,
imaging report, H&P note, clinician note, flowsheet, etc.). Look at both the
text content AND any figures, IHC panels, tables, or images on the page.

You extract a fixed schema of fields. Many pages will mention NONE of them —
that is FINE and expected. When the page has no relevant content, emit the
JSON with every field null / empty. Do NOT reason about whether the document
matches any particular disease. Do NOT explain. Do NOT apologize. Just emit
the JSON, even if it is almost entirely null.

Target fields (extract only what is explicitly stated on THIS page):

  primary_cancer_type — snake_case tumour category, e.g. cutaneous_melanoma,
    lung_adenocarcinoma, lung_squamous, breast_ductal_carcinoma,
    colorectal_adenocarcinoma, gastric_carcinoma, pancreatic_carcinoma,
    prostate_carcinoma, ovarian_carcinoma, renal_cell_carcinoma,
    hepatocellular_carcinoma, bladder_carcinoma, head_neck_scc,
    glioblastoma, lymphoma_dlbcl, multiple_myeloma, other.
    Extract from phrases like "Diagnosis: adenocarcinoma of the lung, RUL" or
    "Nodular melanoma". If the page doesn't state the cancer type, leave null.
  histology — free-text histology, e.g. "adenocarcinoma", "squamous cell
    carcinoma", "ductal carcinoma", "nodular melanoma".
  primary_site — free-text anatomic site, e.g. "right upper lobe lung",
    "left breast, upper outer quadrant", "sigmoid colon", "skin, right shoulder".
  melanoma_subtype — if stated, one of: superficial_spreading, nodular,
    lentigo_maligna, acral_lentiginous, desmoplastic, other.
  breslow_thickness_mm — Breslow depth in mm. Phrases: "Breslow 2.1 mm",
    "depth of invasion 1.8 mm". Number only.
  ulceration — true / false. Phrases: "ulceration: present", "non-ulcerated".
  mitotic_rate_per_mm2 — mitoses per mm². Phrases: "mitotic rate 3/mm²".
    Number only.
  tils_present — tumor-infiltrating lymphocytes. Map to one of: absent,
    non_brisk, brisk.
  pdl1_estimate — PD-L1 IHC. Map TPS/CPS% to: negative (<1%), low (1–49%),
    high (≥50%).
  lag3_ihc_percent — LAG-3 IHC % positive. Number 0–100.
  ajcc_stage — stated AJCC stage (e.g. "IIIA", "IV").
  age_years, ecog, measurable_disease_recist, life_expectancy_months,
  prior_systemic_therapy, prior_anti_pd1 — as stated.
  mutations_text — raw strings of any gene mutations on the page, e.g.
    ["BRAF V600E", "EGFR exon 19 deletion", "NRAS Q61R"]. Include fusions,
    deletions, amplifications as free text. Works for any cancer type.

Hard rules:
* Leave a field null if the page does not state it — do NOT guess.
* Output ONLY a single JSON object. No prose before or after. No markdown
  fences. No <think> block. No "Okay, let me..." preamble. Start your output
  with `{` and end it with `}`.
* If the page has none of these fields, still output a valid JSON object with
  every field null / [] / "". Example for a page that mentions nothing:
    {"page_description": "Infusion flowsheet — no pathology or molecular data",
     "primary_cancer_type": null, "histology": null, "primary_site": null,
     "melanoma_subtype": null, "breslow_thickness_mm": null,
     "ulceration": null, "mitotic_rate_per_mm2": null, "tils_present": null,
     "pdl1_estimate": null, "lag3_ihc_percent": null, "ajcc_stage": null,
     "age_years": null, "ecog": null, "measurable_disease_recist": null,
     "life_expectancy_months": null, "prior_systemic_therapy": null,
     "prior_anti_pd1": null, "mutations_text": [], "relevant_notes": ""}

Worked example 1 — melanoma pathology page:
  "Diagnosis: Nodular melanoma, right shoulder. Breslow 2.3 mm, ulceration
   present. Mitotic rate 4/mm². TILs non-brisk. PD-L1 TPS 15%. LAG-3 IHC 20%.
   Molecular: BRAF V600E detected."
  →
  {"page_description": "Pathology report — primary melanoma findings",
   "primary_cancer_type": "cutaneous_melanoma", "histology": "nodular melanoma",
   "primary_site": "skin, right shoulder",
   "melanoma_subtype": "nodular", "breslow_thickness_mm": 2.3,
   "ulceration": true, "mitotic_rate_per_mm2": 4.0, "tils_present": "non_brisk",
   "pdl1_estimate": "low", "lag3_ihc_percent": 20.0, "ajcc_stage": null,
   "age_years": null, "ecog": null, "measurable_disease_recist": null,
   "life_expectancy_months": null, "prior_systemic_therapy": null,
   "prior_anti_pd1": null, "mutations_text": ["BRAF V600E"],
   "relevant_notes": ""}

Worked example 2 — lung NGS report page:
  "Patient: NSCLC, adenocarcinoma of the right upper lobe, Stage IIIB.
   FoundationOne CDx: EGFR exon 19 deletion (p.E746_A750del) detected.
   PD-L1 TPS 35%."
  →
  {"page_description": "FoundationOne CDx report — EGFR-mutant NSCLC",
   "primary_cancer_type": "lung_adenocarcinoma",
   "histology": "adenocarcinoma",
   "primary_site": "right upper lobe lung",
   "melanoma_subtype": null, "breslow_thickness_mm": null,
   "ulceration": null, "mitotic_rate_per_mm2": null, "tils_present": null,
   "pdl1_estimate": "low", "lag3_ihc_percent": null,
   "ajcc_stage": "IIIB",
   "age_years": null, "ecog": null, "measurable_disease_recist": null,
   "life_expectancy_months": null, "prior_systemic_therapy": null,
   "prior_anti_pd1": null,
   "mutations_text": ["EGFR exon 19 deletion (p.E746_A750del)"],
   "relevant_notes": ""}
"""


_MUT_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})\s+([A-Z])(\d{1,4})([A-Z])\b")


def _regex_mutations(text: str) -> list[Mutation]:
    seen: set[tuple[str, str, int, str]] = set()
    out: list[Mutation] = []
    for m in _MUT_RE.finditer(text):
        gene, ref, pos, alt = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        key = (gene, ref, pos, alt)
        if key in seen:
            continue
        seen.add(key)
        out.append(Mutation(gene=gene, ref_aa=ref, position=pos, alt_aa=alt))
    return out


# ─────────────────────────────────────────────────────────────
# Text + rasterization
# ─────────────────────────────────────────────────────────────


def _pdf_text_per_page(pdf_bytes: bytes, limit: int = MAX_PAGES) -> list[str]:
    """Return page-by-page text via pypdf, capped at `limit` pages."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        return []
    out: list[str] = []
    for i, page in enumerate(reader.pages):
        if i >= limit:
            break
        try:
            out.append(page.extract_text() or "")
        except Exception:
            out.append("")
    return out


def _rasterize_pages(pdf_bytes: bytes, limit: int = MAX_PAGES) -> list[bytes]:
    """Convert up to `limit` PDF pages to JPEG bytes.

    Preferred path: PyMuPDF (``pymupdf``/``fitz``) — pure Python wheels, no
    system poppler dependency, ~5× faster than pdf2image. Falls back to
    pdf2image+poppler when available, otherwise returns [].
    """
    # --- Path 1: PyMuPDF (no system deps) -----------------------------------
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError:
        fitz = None  # type: ignore

    if fitz is not None:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            out: list[bytes] = []
            zoom = RASTER_DPI / 72.0
            mat = fitz.Matrix(zoom, zoom)
            for i, page in enumerate(doc):
                if i >= limit:
                    break
                pix = page.get_pixmap(matrix=mat, alpha=False)
                out.append(pix.tobytes(output="jpeg"))
            doc.close()
            if out:
                return out
        except Exception:
            pass

    # --- Path 2: pdf2image (requires poppler CLI) --------------------------
    try:
        from pdf2image import convert_from_bytes  # type: ignore
    except ImportError:
        return []
    try:
        images = convert_from_bytes(
            pdf_bytes, dpi=RASTER_DPI, first_page=1, last_page=limit,
        )
    except Exception:
        return []
    out2: list[bytes] = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        out2.append(buf.getvalue())
    return out2


# ─────────────────────────────────────────────────────────────
# Per-page VLM call
# ─────────────────────────────────────────────────────────────


async def _analyze_page(
    page_number: int,
    image_bytes: bytes,
    page_text: str,
) -> PageFinding:
    """Run MediX VLM on one page image (plus optional OCR text) → PageFinding."""
    prompt = (
        "You are looking at page "
        f"{page_number} of a patient's medical document. "
        "Extract ONLY what this page explicitly shows.\n\n"
    )
    if page_text.strip():
        prompt += (
            "OCR / text-layer contents of this page (may be noisy):\n---\n"
            f"{page_text[:6000]}\n---\n\n"
        )
    prompt += "Now return the JSON."

    try:
        payload = await call_with_vision(
            schema=_VisionPayload,
            system_prompt=VISION_SYSTEM_PROMPT,
            user_prompt=prompt,
            images=[image_bytes],
            max_tokens=VISION_MAX_TOKENS,
        )
    except Exception as e:
        return PageFinding(
            page_number=page_number,
            description=f"(VLM call failed: {type(e).__name__})",
        )

    return PageFinding(
        page_number=page_number,
        description=payload.page_description,
        primary_cancer_type=payload.primary_cancer_type,
        histology=payload.histology,
        primary_site=payload.primary_site,
        melanoma_subtype=payload.melanoma_subtype,
        breslow_thickness_mm=payload.breslow_thickness_mm,
        ulceration=payload.ulceration,
        mitotic_rate_per_mm2=payload.mitotic_rate_per_mm2,
        tils_present=payload.tils_present,
        pdl1_estimate=payload.pdl1_estimate,
        lag3_ihc_percent=payload.lag3_ihc_percent,
        ajcc_stage=payload.ajcc_stage,
        age_years=payload.age_years,
        ecog=payload.ecog,
        measurable_disease_recist=payload.measurable_disease_recist,
        life_expectancy_months=payload.life_expectancy_months,
        prior_systemic_therapy=payload.prior_systemic_therapy,
        prior_anti_pd1=payload.prior_anti_pd1,
        mutations_text=list(payload.mutations_text or []),
        notes=payload.relevant_notes,
    )


# ─────────────────────────────────────────────────────────────
# Public: extract one document
# ─────────────────────────────────────────────────────────────


def _text_only_page_finding(page_number: int, page_text: str) -> PageFinding:
    muts = _regex_mutations(page_text)
    return PageFinding(
        page_number=page_number,
        description="(text-only fallback — VLM unavailable)",
        mutations_text=[m.full_label for m in muts],
    )


def _guess_document_kind(filename: str, text: str) -> str:
    name = filename.lower()
    sample = (text or "")[:2000].lower()
    if "patholog" in name or "histolog" in sample or "breslow" in sample:
        return "pathology_report"
    if "ngs" in name or "foundation" in name or "oncopanel" in sample or "tmb" in sample:
        return "molecular_report"
    if "imaging" in name or "radiology" in name or "ct " in sample or "pet " in sample:
        return "imaging_report"
    if "h&p" in name or "progress" in name or "ecog" in sample:
        return "clinical_note"
    return "unknown"


async def extract_document(filename: str, pdf_bytes: bytes) -> DocumentExtraction:
    """Extract one PDF — text per page + per-page VLM findings.

    Emits ``DOC_EXTRACTED`` when done. The VLM runs with a bounded concurrency
    sempahore so a 20-page PDF doesn't flood the GH200.
    """
    text_pages = _pdf_text_per_page(pdf_bytes)
    image_pages = _rasterize_pages(pdf_bytes, limit=max(len(text_pages) or MAX_PAGES, MAX_PAGES))
    page_count = max(len(text_pages), len(image_pages))

    findings: list[PageFinding]
    used_vision = False

    if image_pages and has_medix_key():
        used_vision = True
        sem = asyncio.Semaphore(VISION_CONCURRENCY)

        async def _run(i: int) -> PageFinding:
            async with sem:
                text = text_pages[i] if i < len(text_pages) else ""
                return await _analyze_page(i + 1, image_pages[i], text)

        findings = await asyncio.gather(*[_run(i) for i in range(len(image_pages))])
    else:
        findings = [
            _text_only_page_finding(i + 1, text_pages[i] if i < len(text_pages) else "")
            for i in range(page_count or 1)
        ]

    joined_text = "\n\n".join(text_pages)
    doc = DocumentExtraction(
        filename=filename,
        document_kind=_guess_document_kind(filename, joined_text),
        page_count=page_count,
        text_excerpt=joined_text[:3000],
        pages=findings,
        used_vision_fallback=used_vision,
    )
    await emit(
        EventKind.DOC_EXTRACTED,
        f"{filename} · {page_count} pages · "
        f"{sum(1 for p in findings if p.mutations_text)} pages with mutations",
        {
            "filename": filename,
            "document_kind": doc.document_kind,
            "page_count": page_count,
            "used_vision": used_vision,
        },
    )
    return doc


__all__ = ["extract_document", "DocumentExtraction", "PageFinding"]
