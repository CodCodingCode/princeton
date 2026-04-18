"""Pre-build the phase-2+ oncology-trial RAG corpus.

Queries NCBI E-utilities for phase 2+ clinical trial papers across major
cancer types, fetches abstracts, and stores them in a persistent ChromaDB
collection. The store is loaded at runtime by
``backend/src/neoantigen/rag/store.py``.

Quality filter: every search is ANDed with a PubMed publication-type filter
that requires the paper to be a Phase 2, Phase 3, Phase 4, or Randomized
Controlled Trial. This drops preclinical work, phase-1 dose-finding,
case reports, and narrative reviews - which were the main source of noise
in the prior melanoma-only corpus.

Each stored document gets ``cancer_type`` and ``trial_phase`` metadata so
runtime retrieval can filter by cancer when we know the primary diagnosis.

NCBI rate limits unauthenticated traffic to 3 requests/second; with an API
key you get 10/s. Set ``NCBI_API_KEY`` if you have one (free at
https://www.ncbi.nlm.nih.gov/account/) - the script falls back to anonymous
mode otherwise with a slower sleep between calls.

Run from the repo root::

    python backend/scripts/build_pubmed_rag.py

~250–400 MB on disk; runtime 30–60 min with an API key.
"""

from __future__ import annotations

import argparse
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator

import httpx

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "rag"
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# PubMed publication-type filter: only phase 2+ interventional evidence.
PHASE_FILTER = (
    '("Clinical Trial, Phase II"[ptyp] OR '
    '"Clinical Trial, Phase III"[ptyp] OR '
    '"Clinical Trial, Phase IV"[ptyp] OR '
    '"Randomized Controlled Trial"[ptyp])'
)


# {cancer_type: [(topic_label, base_query), ...]}
# The cancer_type key lands in Chroma metadata and is used for runtime filtering.
CANCER_TOPICS: dict[str, list[tuple[str, str]]] = {
    "cutaneous_melanoma": [
        ("melanoma BRAF V600 targeted", "BRAF V600 melanoma AND (dabrafenib OR vemurafenib OR encorafenib OR trametinib)"),
        ("melanoma anti-PD-1", "melanoma AND (pembrolizumab OR nivolumab)"),
        ("melanoma ipilimumab nivolumab combo", "ipilimumab AND nivolumab AND melanoma"),
        ("melanoma LAG-3 relatlimab", "relatlimab AND melanoma"),
        ("melanoma adjuvant stage III", "melanoma AND adjuvant AND (stage III OR resected)"),
    ],
    "lung_adenocarcinoma": [
        ("NSCLC EGFR osimertinib", "EGFR mutation NSCLC AND osimertinib"),
        ("NSCLC ALK", "ALK fusion NSCLC AND (alectinib OR lorlatinib OR brigatinib)"),
        ("NSCLC KRAS G12C", "KRAS G12C NSCLC AND (sotorasib OR adagrasib)"),
        ("NSCLC anti-PD-1 first-line", "pembrolizumab AND NSCLC AND first-line"),
        ("NSCLC MET exon 14", "MET exon 14 NSCLC AND (capmatinib OR tepotinib)"),
    ],
    "breast_carcinoma": [
        ("HER2+ breast trastuzumab", "HER2 positive breast cancer AND trastuzumab"),
        ("HER2-low breast T-DXd", "HER2 low breast cancer AND trastuzumab deruxtecan"),
        ("BRCA breast olaparib", "BRCA breast cancer AND (olaparib OR talazoparib)"),
        ("HR+ CDK4/6", "HR positive breast cancer AND (palbociclib OR ribociclib OR abemaciclib)"),
        ("TNBC pembrolizumab", "triple negative breast cancer AND pembrolizumab"),
    ],
    "colorectal_carcinoma": [
        ("CRC BRAF V600E", "BRAF V600E colorectal AND (encorafenib OR cetuximab)"),
        ("CRC MSI-H IO", "MSI-H colorectal AND (pembrolizumab OR nivolumab)"),
        ("CRC KRAS G12C", "KRAS G12C colorectal AND (adagrasib OR sotorasib)"),
        ("CRC HER2", "HER2 colorectal AND (trastuzumab OR tucatinib)"),
        ("mCRC first-line FOLFOX", "metastatic colorectal AND FOLFOX AND first-line"),
    ],
    "gastric_carcinoma": [
        ("gastric HER2", "gastric cancer AND HER2 AND trastuzumab"),
        ("gastric nivolumab", "gastric cancer AND nivolumab"),
        ("gastric pembrolizumab", "gastric cancer AND pembrolizumab"),
        ("gastric ramucirumab", "gastric cancer AND ramucirumab"),
        ("esophagogastric FLOT", "esophagogastric AND FLOT"),
    ],
    "pancreatic_carcinoma": [
        ("pancreatic FOLFIRINOX", "pancreatic cancer AND FOLFIRINOX"),
        ("pancreatic gemcitabine nab-paclitaxel", "pancreatic cancer AND gemcitabine AND nab-paclitaxel"),
        ("pancreatic BRCA olaparib", "pancreatic cancer AND BRCA AND olaparib"),
        ("pancreatic adjuvant", "pancreatic cancer AND adjuvant"),
    ],
    "prostate_carcinoma": [
        ("mCRPC abiraterone", "metastatic castration resistant prostate AND abiraterone"),
        ("mCRPC enzalutamide", "metastatic castration resistant prostate AND enzalutamide"),
        ("prostate BRCA olaparib", "prostate cancer AND BRCA AND olaparib"),
        ("prostate Lu-177 PSMA", "prostate cancer AND (lutetium OR PSMA-617)"),
        ("prostate docetaxel", "metastatic prostate cancer AND docetaxel"),
    ],
    "ovarian_carcinoma": [
        ("ovarian BRCA PARP", "ovarian cancer AND BRCA AND (olaparib OR niraparib OR rucaparib)"),
        ("ovarian bevacizumab", "ovarian cancer AND bevacizumab"),
        ("ovarian platinum", "ovarian cancer AND platinum"),
        ("ovarian HRD", "ovarian cancer AND homologous recombination deficiency"),
    ],
    "renal_cell_carcinoma": [
        ("RCC anti-PD-1 TKI combo", "renal cell carcinoma AND (pembrolizumab OR nivolumab) AND (axitinib OR cabozantinib OR lenvatinib)"),
        ("RCC ipilimumab nivolumab", "renal cell carcinoma AND ipilimumab AND nivolumab"),
        ("RCC cabozantinib", "renal cell carcinoma AND cabozantinib"),
        ("RCC adjuvant pembrolizumab", "renal cell carcinoma AND adjuvant AND pembrolizumab"),
    ],
    "hepatocellular_carcinoma": [
        ("HCC atezolizumab bevacizumab", "hepatocellular AND atezolizumab AND bevacizumab"),
        ("HCC sorafenib", "hepatocellular AND sorafenib"),
        ("HCC lenvatinib", "hepatocellular AND lenvatinib"),
        ("HCC tremelimumab durvalumab", "hepatocellular AND tremelimumab AND durvalumab"),
    ],
    "bladder_carcinoma": [
        ("bladder enfortumab vedotin", "urothelial AND enfortumab vedotin"),
        ("bladder pembrolizumab", "urothelial AND pembrolizumab"),
        ("bladder FGFR3 erdafitinib", "urothelial AND FGFR AND erdafitinib"),
        ("bladder gemcitabine cisplatin", "urothelial AND gemcitabine AND cisplatin"),
    ],
    "head_neck_scc": [
        ("HNSCC pembrolizumab", "head and neck squamous AND pembrolizumab"),
        ("HNSCC cetuximab", "head and neck squamous AND cetuximab"),
        ("HNSCC nivolumab", "head and neck squamous AND nivolumab"),
        ("HNSCC chemoradiation", "head and neck squamous AND chemoradiation"),
    ],
    "glioblastoma": [
        ("GBM temozolomide", "glioblastoma AND temozolomide"),
        ("GBM bevacizumab", "glioblastoma AND bevacizumab"),
        ("GBM TTFields", "glioblastoma AND tumor treating fields"),
        ("GBM MGMT", "glioblastoma AND MGMT"),
    ],
    "lymphoma_dlbcl": [
        ("DLBCL R-CHOP", "diffuse large B-cell AND R-CHOP"),
        ("DLBCL polatuzumab", "diffuse large B-cell AND polatuzumab"),
        ("DLBCL CAR-T", "diffuse large B-cell AND (axicabtagene OR lisocabtagene OR tisagenlecleucel)"),
        ("DLBCL rituximab", "diffuse large B-cell AND rituximab"),
    ],
    "multiple_myeloma": [
        ("MM daratumumab", "multiple myeloma AND daratumumab"),
        ("MM lenalidomide", "multiple myeloma AND lenalidomide"),
        ("MM bortezomib", "multiple myeloma AND bortezomib"),
        ("MM CAR-T BCMA", "multiple myeloma AND (idecabtagene OR ciltacabtagene)"),
        ("MM bispecific", "multiple myeloma AND (teclistamab OR talquetamab OR elranatamab)"),
    ],
}


def _sleep_for_rate_limit(api_key: str | None) -> None:
    time.sleep(0.12 if api_key else 0.40)


def search_pubmed(query: str, retmax: int, api_key: str | None) -> list[str]:
    filtered = f"({query}) AND {PHASE_FILTER}"
    params = {
        "db": "pubmed",
        "term": filtered,
        "retmax": retmax,
        "retmode": "json",
        "sort": "relevance",
    }
    if api_key:
        params["api_key"] = api_key
    r = httpx.get(ESEARCH, params=params, timeout=30.0)
    r.raise_for_status()
    return r.json()["esearchresult"]["idlist"]


_PHASE_TAG_RE = re.compile(r"Phase\s+(I{1,3}V?|\d+)", re.IGNORECASE)
_ROMAN_TO_INT = {"I": 1, "II": 2, "III": 3, "IV": 4}


def _extract_phase(article: ET.Element) -> str:
    """Pull the trial phase from PublicationTypeList (PT tags)."""
    phases: set[int] = set()
    for pt in article.findall(".//PublicationTypeList/PublicationType"):
        text = (pt.text or "").strip()
        m = _PHASE_TAG_RE.search(text)
        if not m:
            continue
        token = m.group(1).upper()
        if token.isdigit():
            phases.add(int(token))
        elif token in _ROMAN_TO_INT:
            phases.add(_ROMAN_TO_INT[token])
    if phases:
        return str(max(phases))
    # Randomized controlled trials that don't declare a phase - treat as "rct"
    for pt in article.findall(".//PublicationTypeList/PublicationType"):
        if "Randomized Controlled Trial" in (pt.text or ""):
            return "rct"
    return "unknown"


def fetch_abstracts(pmids: list[str], api_key: str | None) -> Iterator[dict]:
    if not pmids:
        return
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
    }
    if api_key:
        params["api_key"] = api_key
    r = httpx.get(EFETCH, params=params, timeout=120.0)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    for art in root.iter("PubmedArticle"):
        pmid_el = art.find(".//PMID")
        title_el = art.find(".//ArticleTitle")
        abstract_pieces = [
            (a.text or "") for a in art.findall(".//Abstract/AbstractText")
        ]
        year_el = art.find(".//PubDate/Year") or art.find(".//PubDate/MedlineDate")
        journal_el = art.find(".//Journal/Title")
        if pmid_el is None or title_el is None or not abstract_pieces:
            continue
        yield {
            "pmid": pmid_el.text or "",
            "title": (title_el.text or "").strip(),
            "abstract": " ".join(s.strip() for s in abstract_pieces if s),
            "year": (year_el.text if year_el is not None else "")[:4],
            "journal": (journal_el.text or "").strip() if journal_el is not None else "",
            "trial_phase": _extract_phase(art),
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-query", type=int, default=80, help="abstracts per query")
    ap.add_argument("--collection", default="oncology_trials_phase2plus")
    args = ap.parse_args()

    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        raise SystemExit("chromadb missing - install with: pip install -e './backend[rag]'")

    api_key = os.environ.get("NCBI_API_KEY")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(OUT_DIR))
    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    try:
        client.delete_collection(args.collection)
    except Exception:
        pass
    coll = client.create_collection(name=args.collection, embedding_function=embedder)

    seen_pmids: set[str] = set()
    total = 0
    for cancer_type, topics in CANCER_TOPICS.items():
        print(f"\n══ {cancer_type} ══")
        for topic, query in topics:
            print(f"  → {topic}")
            pmids = search_pubmed(query, args.per_query, api_key)
            _sleep_for_rate_limit(api_key)
            new_pmids = [p for p in pmids if p not in seen_pmids]
            if not new_pmids:
                print("    (no new papers)")
                continue
            seen_pmids.update(new_pmids)

            # Batch efetch in chunks of 50 (NCBI prefers smaller ID lists)
            for i in range(0, len(new_pmids), 50):
                chunk = new_pmids[i : i + 50]
                documents, metadatas, ids = [], [], []
                for paper in fetch_abstracts(chunk, api_key):
                    doc = f"{paper['title']}. {paper['abstract']}"
                    documents.append(doc)
                    metadatas.append({
                        "pmid": paper["pmid"],
                        "title": paper["title"],
                        "year": paper["year"],
                        "journal": paper["journal"],
                        "topic": topic,
                        "cancer_type": cancer_type,
                        "trial_phase": paper["trial_phase"],
                    })
                    ids.append(paper["pmid"])
                if documents:
                    coll.add(documents=documents, metadatas=metadatas, ids=ids)
                    total += len(documents)
                    print(f"    +{len(documents)} (running total {total})")
                _sleep_for_rate_limit(api_key)

    print(f"\n✓ stored {total} unique phase-2+ abstracts in {OUT_DIR}")
    print(f"  collection: {args.collection}")
    print(f"  cancer types: {len(CANCER_TOPICS)}")


if __name__ == "__main__":
    main()
