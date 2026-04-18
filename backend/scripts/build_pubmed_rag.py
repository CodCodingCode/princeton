"""Pre-build the PubMed-backed RAG knowledge base.

Queries NCBI E-utilities for melanoma-relevant papers, fetches abstracts, and
stores them in a persistent ChromaDB collection. The RAG store is loaded by
``backend/src/neoantigen/rag/store.py`` at runtime.

NCBI rate limits unauthenticated traffic to 3 requests/second; with an API key
you get 10/s. Set ``NCBI_API_KEY`` if you have one (free at
https://www.ncbi.nlm.nih.gov/account/) — the script falls back to anonymous
mode otherwise with a slower sleep between calls.

Run from the repo root::

    python backend/scripts/build_pubmed_rag.py

About 100-150 MB on disk; runtime 15-30 minutes depending on rate limits.
"""

from __future__ import annotations

import argparse
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator

import httpx

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "rag"
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

QUERIES: dict[str, str] = {
    "BRAF V600E melanoma immunotherapy": "BRAF V600E AND melanoma AND immunotherapy",
    "BRAF V600E targeted therapy": "(BRAF V600E AND melanoma) AND (dabrafenib OR vemurafenib OR trametinib)",
    "NRAS Q61 melanoma": "NRAS Q61 AND melanoma AND treatment",
    "KIT melanoma": "KIT mutation AND melanoma AND (imatinib OR sunitinib)",
    "NF1 melanoma": "NF1 mutation AND melanoma",
    "anti-PD-1 melanoma": "(pembrolizumab OR nivolumab) AND melanoma AND (response OR survival)",
    "ipilimumab nivolumab combo melanoma": "ipilimumab AND nivolumab AND melanoma",
    "neoantigen vaccine melanoma": "neoantigen AND vaccine AND melanoma",
    "tumor mutational burden melanoma": "tumor mutational burden AND melanoma AND immunotherapy",
    "melanoma adjuvant therapy stage III": "melanoma AND adjuvant AND (stage III OR resected) AND therapy",
    "melanoma brain metastases": "melanoma AND brain metastases AND treatment",
    "BRAF MEK inhibitor resistance": "BRAF inhibitor AND melanoma AND (resistance OR escape)",
    "AJCC melanoma staging": "AJCC AND melanoma AND staging",
    "Breslow thickness sentinel lymph node": "Breslow AND sentinel lymph node AND melanoma",
    "PD-L1 melanoma response": "PD-L1 AND melanoma AND (response OR predictive)",
}


def _sleep_for_rate_limit(api_key: str | None) -> None:
    time.sleep(0.12 if api_key else 0.40)


def search_pubmed(query: str, retmax: int, api_key: str | None) -> list[str]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retmode": "json",
        "sort": "relevance",
    }
    if api_key:
        params["api_key"] = api_key
    r = httpx.get(ESEARCH, params=params, timeout=30.0)
    r.raise_for_status()
    return r.json()["esearchresult"]["idlist"]


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
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-query", type=int, default=80, help="abstracts per query")
    ap.add_argument("--collection", default="melanoma_papers")
    args = ap.parse_args()

    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        raise SystemExit("chromadb missing — install with: pip install -e './backend[rag]'")

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
    for topic, query in QUERIES.items():
        print(f"→ {topic}")
        pmids = search_pubmed(query, args.per_query, api_key)
        _sleep_for_rate_limit(api_key)
        new_pmids = [p for p in pmids if p not in seen_pmids]
        if not new_pmids:
            print("  (no new papers)")
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
                })
                ids.append(paper["pmid"])
            if documents:
                coll.add(documents=documents, metadatas=metadatas, ids=ids)
                total += len(documents)
                print(f"  +{len(documents)} (running total {total})")
            _sleep_for_rate_limit(api_key)

    print(f"\n✓ stored {total} unique abstracts in {OUT_DIR}")


if __name__ == "__main__":
    main()
