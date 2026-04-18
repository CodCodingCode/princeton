"""Per-PDF extraction - text + per-page MediX VLM vision findings.

Single entrypoint: ``extract_document(filename, pdf_bytes) -> DocumentExtraction``.

For each page:
  1. pypdf text extraction (best-effort).
  2. Rasterize the page to JPEG.
  3. Hand the page image to MediX (Qwen3-VL-based, GH200 vLLM tunnel) asking
     for any oncology-relevant findings on that page, structured as a
     ``PageFinding``.

Every call is best-effort - missing deps / offline tunnels degrade to empty
findings rather than raising.
"""

from __future__ import annotations

import asyncio
import io
import re

from pydantic import BaseModel, Field

from ..agent._llm import call_for_json, call_with_vision, has_api_key, has_medix_key
from ..agent.audit import audit
from ..agent.events import EventKind, emit
from ..models import DocumentExtraction, Mutation, PageFinding


MAX_PAGES = 20          # Hard cap per PDF to keep per-case latency bounded.
RASTER_DPI = 150
# K2-Think V2 emits a <think> block before the JSON. On a dense pathology or
# fax page the reasoning alone can run 1-2k tokens, so 1200 was tripping
# max_tokens mid-JSON and producing the "model did not return valid JSON"
# errors that users saw as "(VLM call failed: ValueError)" in the Documents
# tab. 2500 gives headroom without materially increasing cost.
VISION_MAX_TOKENS = 2500
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

You extract a fixed schema of fields. Many pages will mention NONE of them -
that is FINE and expected. When the page has no relevant content, emit the
JSON with every field null / empty. Do NOT reason about whether the document
matches any particular disease. Do NOT explain. Do NOT apologize. Just emit
the JSON, even if it is almost entirely null.

Target fields (extract only what is explicitly stated on THIS page):

  primary_cancer_type - snake_case tumour category, e.g. cutaneous_melanoma,
    lung_adenocarcinoma, lung_squamous, breast_ductal_carcinoma,
    colorectal_adenocarcinoma, gastric_carcinoma, pancreatic_carcinoma,
    prostate_carcinoma, ovarian_carcinoma, renal_cell_carcinoma,
    hepatocellular_carcinoma, bladder_carcinoma, head_neck_scc,
    glioblastoma, lymphoma_dlbcl, multiple_myeloma, other.
    Extract from phrases like "Diagnosis: adenocarcinoma of the lung, RUL" or
    "Nodular melanoma". If the page doesn't state the cancer type, leave null.
  histology - free-text histology, e.g. "adenocarcinoma", "squamous cell
    carcinoma", "ductal carcinoma", "nodular melanoma".
  primary_site - free-text anatomic site, e.g. "right upper lobe lung",
    "left breast, upper outer quadrant", "sigmoid colon", "skin, right shoulder".
  melanoma_subtype - if stated, one of: superficial_spreading, nodular,
    lentigo_maligna, acral_lentiginous, desmoplastic, other.
  breslow_thickness_mm - Breslow depth in mm. Phrases: "Breslow 2.1 mm",
    "depth of invasion 1.8 mm". Number only.
  ulceration - true / false. Phrases: "ulceration: present", "non-ulcerated".
  mitotic_rate_per_mm2 - mitoses per mm². Phrases: "mitotic rate 3/mm²".
    Number only.
  tils_present - tumor-infiltrating lymphocytes. Map to one of: absent,
    non_brisk, brisk.
  pdl1_estimate - PD-L1 IHC. Map TPS/CPS% to: negative (<1%), low (1–49%),
    high (≥50%).
  lag3_ihc_percent - LAG-3 IHC % positive. Number 0–100.
  ajcc_stage - stated AJCC stage (e.g. "IIIA", "IV").
  age_years, ecog, measurable_disease_recist, life_expectancy_months,
  prior_systemic_therapy, prior_anti_pd1 - as stated.
  mutations_text - raw strings of any gene mutations on the page, e.g.
    ["BRAF V600E", "EGFR exon 19 deletion", "NRAS Q61R"]. Include fusions,
    deletions, amplifications as free text. Works for any cancer type.

Hard rules:
* Leave a field null if the page does not state it - do NOT guess.
* Output ONLY a single JSON object. No prose before or after. No markdown
  fences. No <think> block. No "Okay, let me..." preamble. Start your output
  with `{` and end it with `}`.
* If the page has none of these fields, still output a valid JSON object with
  every field null / [] / "". Example for a page that mentions nothing:
    {"page_description": "Infusion flowsheet - no pathology or molecular data",
     "primary_cancer_type": null, "histology": null, "primary_site": null,
     "melanoma_subtype": null, "breslow_thickness_mm": null,
     "ulceration": null, "mitotic_rate_per_mm2": null, "tils_present": null,
     "pdl1_estimate": null, "lag3_ihc_percent": null, "ajcc_stage": null,
     "age_years": null, "ecog": null, "measurable_disease_recist": null,
     "life_expectancy_months": null, "prior_systemic_therapy": null,
     "prior_anti_pd1": null, "mutations_text": [], "relevant_notes": ""}

Worked example 1 - melanoma pathology page:
  "Diagnosis: Nodular melanoma, right shoulder. Breslow 2.3 mm, ulceration
   present. Mitotic rate 4/mm². TILs non-brisk. PD-L1 TPS 15%. LAG-3 IHC 20%.
   Molecular: BRAF V600E detected."
  →
  {"page_description": "Pathology report - primary melanoma findings",
   "primary_cancer_type": "cutaneous_melanoma", "histology": "nodular melanoma",
   "primary_site": "skin, right shoulder",
   "melanoma_subtype": "nodular", "breslow_thickness_mm": 2.3,
   "ulceration": true, "mitotic_rate_per_mm2": 4.0, "tils_present": "non_brisk",
   "pdl1_estimate": "low", "lag3_ihc_percent": 20.0, "ajcc_stage": null,
   "age_years": null, "ecog": null, "measurable_disease_recist": null,
   "life_expectancy_months": null, "prior_systemic_therapy": null,
   "prior_anti_pd1": null, "mutations_text": ["BRAF V600E"],
   "relevant_notes": ""}

Worked example 2 - lung NGS report page:
  "Patient: NSCLC, adenocarcinoma of the right upper lobe, Stage IIIB.
   FoundationOne CDx: EGFR exon 19 deletion (p.E746_A750del) detected.
   PD-L1 TPS 35%."
  →
  {"page_description": "FoundationOne CDx report - EGFR-mutant NSCLC",
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

    Preferred path: PyMuPDF (``pymupdf``/``fitz``) - pure Python wheels, no
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


def _payload_to_finding(page_number: int, payload: "_VisionPayload") -> PageFinding:
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


def _count_populated(payload: "_VisionPayload") -> int:
    """Count non-null/non-empty structured fields the model returned."""
    fields = (
        payload.primary_cancer_type, payload.histology, payload.primary_site,
        payload.melanoma_subtype, payload.breslow_thickness_mm,
        payload.ulceration, payload.mitotic_rate_per_mm2, payload.tils_present,
        payload.pdl1_estimate, payload.lag3_ihc_percent, payload.ajcc_stage,
        payload.age_years, payload.ecog, payload.measurable_disease_recist,
        payload.life_expectancy_months, payload.prior_systemic_therapy,
        payload.prior_anti_pd1,
    )
    return sum(
        1 for v in fields
        if v is not None and v != "" and str(v).lower() != "unknown"
    )


async def _analyze_page_text(
    page_number: int, page_text: str, filename: str = "unknown",
) -> PageFinding:
    """Run Kimi K2 on page text only (no image). Raises on failure; the
    per-page fallback chain in ``extract_document`` catches and retries with
    the VLM path."""
    import time as _time
    prompt = (
        f"You are reading page {page_number} of a patient's medical document.\n"
        "Below is the text layer extracted from this page. Extract ONLY what is\n"
        "explicitly stated here. Then return the JSON per the system schema.\n\n"
        "--- page text ---\n"
        f"{page_text[:8000]}\n"
        "--- end page text ---\n\n"
        "Return the JSON now."
    )
    t0 = _time.time()
    try:
        payload = await call_for_json(
            schema=_VisionPayload,
            system_prompt=VISION_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=VISION_MAX_TOKENS,
        )
    except Exception as e:
        audit(
            "extractor", "page_error",
            filename=filename, page_number=page_number, modality="text",
            text_len=len(page_text),
            error_type=type(e).__name__, error=str(e),
            latency_ms=int((_time.time() - t0) * 1000),
            text_slice=page_text[:1500],
        )
        raise
    audit(
        "extractor", "page_done",
        filename=filename, page_number=page_number, modality="text",
        text_len=len(page_text),
        fields_populated=_count_populated(payload),
        mutations=len(payload.mutations_text or []),
        latency_ms=int((_time.time() - t0) * 1000),
    )
    return _payload_to_finding(page_number, payload)


async def _analyze_page(
    page_number: int,
    image_bytes: bytes,
    page_text: str,
    filename: str = "unknown",
) -> PageFinding:
    """Run the vision pipeline on one rasterized page. Raises on failure."""
    import time as _time
    prompt = (
        "You are looking at page "
        f"{page_number} of a patient's medical document. "
        "Extract ONLY what this page explicitly shows.\n\n"
    )
    if page_text.strip():
        prompt += (
            "OCR / text-layer contents of this page (may be noisy, scanned, "
            "or upside-down fax artefacts — trust your eyes over this text):\n"
            "---\n"
            f"{page_text[:6000]}\n---\n\n"
        )
    prompt += (
        "Read the image carefully. If the page is a fax or scan, the text "
        "layer is probably garbage and you should rely on the visual content. "
        "Now return the JSON."
    )
    t0 = _time.time()
    try:
        payload = await call_with_vision(
            schema=_VisionPayload,
            system_prompt=VISION_SYSTEM_PROMPT,
            user_prompt=prompt,
            images=[image_bytes],
            max_tokens=VISION_MAX_TOKENS,
        )
    except Exception as e:
        audit(
            "extractor", "page_error",
            filename=filename, page_number=page_number, modality="vision",
            text_len=len(page_text), image_bytes=len(image_bytes),
            error_type=type(e).__name__, error=str(e),
            latency_ms=int((_time.time() - t0) * 1000),
        )
        raise
    audit(
        "extractor", "page_done",
        filename=filename, page_number=page_number, modality="vision",
        text_len=len(page_text), image_bytes=len(image_bytes),
        fields_populated=_count_populated(payload),
        mutations=len(payload.mutations_text or []),
        latency_ms=int((_time.time() - t0) * 1000),
    )
    return _payload_to_finding(page_number, payload)


# ─────────────────────────────────────────────────────────────
# Text-quality and fax-detection heuristics
#
# pypdf's text extraction on faxed / scanned PDFs routinely returns >200
# characters of OCR noise — symbols, fragmented words, and misaligned
# whitespace. The old dispatch chose text-only whenever `len(text) >= 200`,
# which fed that noise to Kimi and triggered "(text-only LLM call failed)".
# These helpers detect those pages so we prefer the VLM path instead.
# ─────────────────────────────────────────────────────────────


def _text_looks_reliable(text: str) -> bool:
    """Heuristic: is this a clean text layer or OCR/fax garbage?

    Real typed text usually has (a) a high alphabetic ratio, (b) plenty of
    whole words of length 3+, and (c) lines that aren't mostly single chars.
    """
    stripped = text.strip()
    if len(stripped) < 150:
        return False
    non_ws = "".join(c for c in stripped if not c.isspace())
    if not non_ws:
        return False
    alpha_ratio = sum(1 for c in non_ws if c.isalpha()) / len(non_ws)
    if alpha_ratio < 0.60:
        return False
    words = stripped.split()
    real_words = sum(
        1 for w in words if len(w) >= 3 and any(c.isalpha() for c in w)
    )
    if real_words < 15:
        return False
    return True


_FAX_HINTS = ("fax", "scan", "scanned", "faxed")


def _filename_looks_like_fax(filename: str) -> bool:
    low = filename.lower()
    return any(tok in low for tok in _FAX_HINTS)


async def _analyze_with_fallback(
    page_number: int,
    page_text: str,
    image_bytes: bytes | None,
    *,
    prefer_vlm: bool,
    llm_ok: bool,
    vlm_ok: bool,
) -> tuple[PageFinding, bool]:
    """Try preferred modality; on failure, try the other; then regex-only.

    Returns ``(finding, used_vision_successfully)``. The second value lets the
    caller track whether any page in a document actually exercised the VLM,
    which drives the ``used_vision_fallback`` flag on ``DocumentExtraction``.
    """

    attempts: list[str] = []
    has_text = llm_ok and bool(page_text.strip())
    has_image = vlm_ok and image_bytes is not None

    if prefer_vlm and has_image:
        attempts.append("vlm")
    if has_text:
        attempts.append("text")
    if not prefer_vlm and has_image and "vlm" not in attempts:
        attempts.append("vlm")

    last_err: Exception | None = None
    for modality in attempts:
        try:
            if modality == "text":
                return await _analyze_page_text(page_number, page_text), False
            else:
                finding = await _analyze_page(
                    page_number, image_bytes or b"", page_text
                )
                return finding, True
        except Exception as e:  # noqa: BLE001 - we want EVERY failure to fall through
            last_err = e
            continue

    # Everything above failed. Produce a useful PageFinding anyway: regex
    # mutations from whatever text we have, plus an honest description that
    # surfaces the first slice of raw text so the user can see what was on
    # the page instead of the useless "(VLM call failed: ValueError)" tail.
    muts = _regex_mutations(page_text) if page_text else []
    excerpt = " ".join(page_text.split())[:180] if page_text else ""
    if last_err is not None:
        tried = ", ".join(attempts) or "none"
        desc = (
            f"Couldn't auto-structure this page (tried {tried}; "
            f"{type(last_err).__name__})."
        )
    else:
        desc = "No extraction path available for this page."
    if excerpt:
        desc += f" Text excerpt: {excerpt}"
    return (
        PageFinding(
            page_number=page_number,
            description=desc,
            mutations_text=[m.full_label for m in muts],
        ),
        False,
    )


# ─────────────────────────────────────────────────────────────
# Public: extract one document
# ─────────────────────────────────────────────────────────────


def _text_only_page_finding(page_number: int, page_text: str) -> PageFinding:
    muts = _regex_mutations(page_text)
    return PageFinding(
        page_number=page_number,
        description="(text-only fallback - VLM unavailable)",
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


_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".html", ".htm", ".log", ".rtf"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp", ".gif"}


def _decode_text(data: bytes) -> str:
    # Best-effort decode - UTF-8 first, Latin-1 as an "never fails" fallback.
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


async def extract_document(filename: str, pdf_bytes: bytes) -> DocumentExtraction:
    """Extract one document - PDF, text file, or image.

    Dispatches by extension:
      * PDF → pypdf text + per-page VLM vision
      * Text-like (.txt/.md/.csv/.json/.html/.log/.rtf) → read as UTF-8, single
        text-only PageFinding with regex-extracted mutations
      * Image (.png/.jpg/.webp/.tiff/.bmp/.gif) → single-page VLM call on the
        raw image bytes

    Emits ``DOC_EXTRACTED`` when done. The VLM runs with a bounded concurrency
    semaphore so a 20-page PDF doesn't flood the GH200.
    """
    lname = filename.lower()
    ext = "." + lname.rsplit(".", 1)[-1] if "." in lname else ""

    # ── Text files ──────────────────────────────────────────────────────────
    if ext in _TEXT_EXTS:
        text = _decode_text(pdf_bytes)
        if has_api_key() and len(text.strip()) >= 200:
            finding, _ = await _analyze_with_fallback(
                page_number=1,
                page_text=text,
                image_bytes=None,
                prefer_vlm=False,
                llm_ok=True,
                vlm_ok=False,
            )
        else:
            finding = PageFinding(
                page_number=1,
                description=f"Text document ({ext[1:]}) · {len(text)} chars",
                mutations_text=[m.full_label for m in _regex_mutations(text)],
            )
        doc = DocumentExtraction(
            filename=filename,
            document_kind=_guess_document_kind(filename, text),
            page_count=1,
            text_excerpt=text[:3000],
            pages=[finding],
            used_vision_fallback=False,
        )
        await emit(
            EventKind.DOC_EXTRACTED,
            f"{filename} · text · {len(text)} chars",
            {
                "filename": filename,
                "document_kind": doc.document_kind,
                "page_count": 1,
                "used_vision": False,
            },
        )
        return doc

    # ── Image files (single-page VLM on the raw bytes) ──────────────────────
    if ext in _IMAGE_EXTS:
        if has_medix_key():
            finding, used_vision = await _analyze_with_fallback(
                page_number=1,
                page_text="",
                image_bytes=pdf_bytes,
                prefer_vlm=True,
                llm_ok=has_api_key(),
                vlm_ok=True,
            )
        else:
            finding = PageFinding(
                page_number=1,
                description=f"Image ({ext[1:]}) - VLM unavailable.",
            )
            used_vision = False
        doc = DocumentExtraction(
            filename=filename,
            document_kind=_guess_document_kind(filename, finding.description or ""),
            page_count=1,
            text_excerpt="",
            pages=[finding],
            used_vision_fallback=used_vision,
        )
        await emit(
            EventKind.DOC_EXTRACTED,
            f"{filename} · image · VLM={used_vision}",
            {
                "filename": filename,
                "document_kind": doc.document_kind,
                "page_count": 1,
                "used_vision": used_vision,
            },
        )
        return doc

    # ── PDF path (default) ──────────────────────────────────────────────────
    text_pages = _pdf_text_per_page(pdf_bytes)
    image_pages = _rasterize_pages(pdf_bytes, limit=max(len(text_pages) or MAX_PAGES, MAX_PAGES))
    page_count = max(len(text_pages), len(image_pages))

    findings: list[PageFinding]
    used_vision = False

    # Per-page dispatch with fallback chain. Two signals decide the preferred
    # modality for each page:
    #   * Filename hint (contains "fax" / "scan") → prefer VLM; pypdf text
    #     layers on fax PDFs are usually OCR garbage.
    #   * Text quality heuristic → if the extracted text looks like noise
    #     (low alphabetic ratio, few real words), prefer VLM.
    #   * Otherwise → prefer text-only (fast, cheap, accurate on typed PDFs).
    #
    # Whichever modality runs first, if it raises (JSON parse failure,
    # truncation, transport error) we try the other. If BOTH fail we still
    # emit a PageFinding with regex-extracted mutations and a human-readable
    # description instead of "(VLM call failed: ValueError)".
    llm_ok = has_api_key()
    vlm_ok = bool(image_pages) and has_medix_key()
    fax_doc = _filename_looks_like_fax(filename)

    if llm_ok or vlm_ok:
        sem = asyncio.Semaphore(VISION_CONCURRENCY)
        any_vision = False

        async def _run(i: int) -> PageFinding:
            nonlocal any_vision
            text = text_pages[i] if i < len(text_pages) else ""
            img = image_pages[i] if i < len(image_pages) else None
            prefer_vlm = fax_doc or not _text_looks_reliable(text)
            async with sem:
                finding, used_v = await _analyze_with_fallback(
                    page_number=i + 1,
                    page_text=text,
                    image_bytes=img,
                    prefer_vlm=prefer_vlm,
                    llm_ok=llm_ok,
                    vlm_ok=vlm_ok and img is not None,
                )
                if used_v:
                    any_vision = True
                return finding

        findings = await asyncio.gather(
            *[_run(i) for i in range(page_count or 1)]
        )
        used_vision = any_vision
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
