"""Lazy ChromaDB wrapper for the phase-2+ oncology-trial corpus.

The store is built ahead of time by ``backend/scripts/build_pubmed_rag.py``.
At runtime we open it read-only, embed the query with the same
sentence-transformers model, and return the top-K nearest abstracts -
optionally filtered by cancer type so a NSCLC case doesn't get melanoma
trials retrieved.

If the store doesn't exist (no pre-build) ``has_store()`` returns False and
the rest of the system gracefully skips RAG augmentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "rag"
COLLECTION = "oncology_trials_phase2plus"

# Legacy collections to try if the current one is missing - lets an existing
# melanoma-only corpus keep working after the upgrade until it's rebuilt.
_LEGACY_COLLECTIONS = ("melanoma_papers",)


@dataclass
class Citation:
    pmid: str
    title: str
    year: str
    journal: str
    snippet: str
    relevance: float
    cancer_type: str = ""
    trial_phase: str = ""

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
    # Prefer the current collection; fall back to any legacy collection that
    # happens to exist on disk from a previous build.
    for name in (COLLECTION, *_LEGACY_COLLECTIONS):
        try:
            coll = client.get_collection(name=name, embedding_function=embedder)
            return client, coll
        except Exception:
            continue
    raise RuntimeError(
        f"No Chroma collection found. Run build_pubmed_rag.py to create {COLLECTION!r}."
    )


def query_papers(
    query: str,
    *,
    top_k: int = 5,
    cancer_type: str | None = None,
    min_phase: int = 2,
) -> list[Citation]:
    """Semantic search over the phase-2+ oncology corpus.

    Args:
        query: natural-language query (embedded with the corpus embedder).
        top_k: max citations to return.
        cancer_type: if given, restrict to papers tagged with this cancer type.
            Falls back to an unfiltered retrieval if the filtered query returns
            zero hits (useful when the corpus doesn't yet cover the cancer).
        min_phase: minimum trial phase to include. The corpus is pre-filtered
            at build time to phase 2+, so this is usually a no-op.
    """
    if not has_store():
        return []
    try:
        _, coll = _client_and_collection()
    except Exception:
        return []

    where = _build_where(cancer_type=cancer_type)

    # First pass: filtered.
    citations = _run_query(coll, query, top_k, where)
    # If filtering produced nothing, try unfiltered so a rare-cancer case still
    # gets some literature back.
    if not citations and where:
        citations = _run_query(coll, query, top_k, None)

    # Honour min_phase if set (again, corpus already pre-filtered - this is a
    # safety net).
    if min_phase and min_phase > 2:
        citations = [c for c in citations if _phase_geq(c.trial_phase, min_phase)]

    return citations


def _build_where(*, cancer_type: str | None) -> dict | None:
    if cancer_type and cancer_type != "unknown":
        return {"cancer_type": cancer_type}
    return None


def _run_query(coll, query: str, top_k: int, where: dict | None) -> list[Citation]:
    try:
        kwargs = {"query_texts": [query], "n_results": top_k}
        if where is not None:
            kwargs["where"] = where
        result = coll.query(**kwargs)
    except Exception:
        return []

    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = result.get("distances", [[]])[0]
    out: list[Citation] = []
    for doc, meta, dist in zip(docs, metas, dists):
        snippet = (doc or "")[:140].rsplit(" ", 1)[0]
        out.append(Citation(
            pmid=str(meta.get("pmid", "")),
            title=str(meta.get("title", "")),
            year=str(meta.get("year", "")),
            journal=str(meta.get("journal", "")),
            snippet=snippet,
            relevance=round(1.0 - float(dist or 0.0), 3),
            cancer_type=str(meta.get("cancer_type", "")),
            trial_phase=str(meta.get("trial_phase", "")),
        ))
    return out


def _phase_geq(phase: str, minimum: int) -> bool:
    if not phase or phase == "unknown":
        return False
    if phase == "rct":  # RCTs without an explicit phase tag pass the >=2 bar
        return minimum <= 2
    try:
        return int(phase) >= minimum
    except ValueError:
        return False
