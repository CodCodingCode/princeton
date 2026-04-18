"""Lazy ChromaDB wrapper that the NCCN walker calls per-node.

The store is built ahead of time by ``backend/scripts/build_pubmed_rag.py``.
At runtime we open it read-only, embed the query string with the same
sentence-transformers model, and return the top-K nearest abstracts.

If the store doesn't exist (no pre-build) ``has_store()`` returns False and
the rest of the system gracefully skips RAG augmentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "rag"
COLLECTION = "melanoma_papers"


@dataclass
class Citation:
    pmid: str
    title: str
    year: str
    journal: str
    snippet: str
    relevance: float

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"


def has_store() -> bool:
    return DATA_DIR.exists() and any(DATA_DIR.iterdir())


@lru_cache(maxsize=1)
def _client_and_collection():
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(DATA_DIR))
    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    coll = client.get_collection(name=COLLECTION, embedding_function=embedder)
    return client, coll


def query_papers(query: str, *, top_k: int = 3) -> list[Citation]:
    """Semantic search over the pre-built PubMed corpus."""
    if not has_store():
        return []
    try:
        _, coll = _client_and_collection()
    except Exception:
        return []
    try:
        result = coll.query(query_texts=[query], n_results=top_k)
    except Exception:
        return []

    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = result.get("distances", [[]])[0]
    out: list[Citation] = []
    for doc, meta, dist in zip(docs, metas, dists):
        snippet = (doc or "")[:280].rsplit(" ", 1)[0]
        out.append(Citation(
            pmid=str(meta.get("pmid", "")),
            title=str(meta.get("title", "")),
            year=str(meta.get("year", "")),
            journal=str(meta.get("journal", "")),
            snippet=snippet,
            relevance=round(1.0 - float(dist or 0.0), 3),
        ))
    return out
