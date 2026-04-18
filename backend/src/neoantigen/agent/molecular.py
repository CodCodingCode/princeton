"""Build the molecular landscape (Panel 2 data).

For each driver mutation we produce a `MoleculeView` that carries:
* The wild-type protein folded with ESMFold (cached under ~/.cache/neoantigen/proteins_pdb).
* The mutant protein folded with ESMFold.
* If the gene is in `DRUG_COCRYSTALS`, the corresponding drug-target co-crystal
  PDB fetched once from RCSB and cached on disk.

We deliberately use known co-crystals rather than running DiffDock at runtime —
docking the right cancer-drug+oncoprotein pair via a public ID is faster, more
accurate for known pairs, and trivial to demo on stage.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

import httpx

from ..models import Mutation, MoleculeView
from ..pipeline.protein import apply_mutation, fetch_protein
from .events import EventKind, emit
from .structure import fold_protein


# Known oncogene drug co-crystals from the RCSB PDB.
# Format: { GENE: [(pdb_id, drug_name), ...] }
DRUG_COCRYSTALS: dict[str, list[tuple[str, str]]] = {
    "BRAF": [("4XV2", "Dabrafenib"), ("3OG7", "Vemurafenib")],
    "KIT":  [("1T46", "Imatinib"),    ("3G0E", "Sunitinib")],
    "MAP2K1": [("3W8Q", "Trametinib")],
    "MAP2K2": [("3W8Q", "Trametinib")],
    "EGFR": [("4ZAU", "Osimertinib")],
    "PIK3CA": [("4JPS", "Alpelisib")],
    "NRAS": [("6ZIZ", "Sotorasib (analog binding pocket)")],
}

PRIORITY_GENES = {"BRAF", "NRAS", "KIT", "NF1", "MAP2K1", "EGFR", "PIK3CA"}


def _pdb_cache_dir() -> Path:
    root = Path(os.environ.get("NEOANTIGEN_CACHE", Path.home() / ".cache" / "neoantigen"))
    path = root / "molecular"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _seq_cache_key(seq: str) -> str:
    return hashlib.sha1(seq.encode()).hexdigest()[:16]


async def _fetch_rcsb_pdb(pdb_id: str, client: httpx.AsyncClient) -> str | None:
    cache = _pdb_cache_dir() / f"rcsb_{pdb_id.lower()}.pdb"
    if cache.exists():
        return cache.read_text()
    url = f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
    try:
        r = await client.get(url, timeout=30.0)
        if r.status_code == 200 and r.text.lstrip().startswith(("HEADER", "ATOM", "REMARK")):
            cache.write_text(r.text)
            return r.text
    except Exception:
        return None
    return None


async def _fold_with_cache(seq: str) -> tuple[str | None, str]:
    key = _seq_cache_key(seq)
    cache = _pdb_cache_dir() / f"esm_{key}.pdb"
    if cache.exists():
        return cache.read_text(), "esmfold"
    pdb, method = await fold_protein(seq)
    if pdb:
        cache.write_text(pdb)
    return pdb, method


def _truncate_for_esmfold(seq: str, mut_pos_1based: int, window: int = 220) -> tuple[str, int]:
    """ESMFold is rate-limited above ~400 aa on the public API. Centre a window on the mutation."""
    if len(seq) <= window:
        return seq, mut_pos_1based
    half = window // 2
    start = max(0, mut_pos_1based - 1 - half)
    end = min(len(seq), start + window)
    start = max(0, end - window)
    return seq[start:end], mut_pos_1based - start


async def build_molecule_view(mutation: Mutation, client: httpx.AsyncClient) -> MoleculeView | None:
    try:
        wt_full = fetch_protein(mutation.gene)
    except (KeyError, httpx.HTTPError):
        await emit(EventKind.LOG, f"Skip molecular view — no UniProt for {mutation.gene}")
        return None

    try:
        mut_full = apply_mutation(wt_full, mutation)
    except ValueError as e:
        await emit(EventKind.LOG, f"Skip molecular view — {e}")
        return None

    wt_window, _ = _truncate_for_esmfold(wt_full, mutation.position)
    mut_window, mut_window_pos = _truncate_for_esmfold(mut_full, mutation.position)

    wt_pdb, method = await _fold_with_cache(wt_window)
    mut_pdb, _ = await _fold_with_cache(mut_window)

    drug_pdb_id = None
    drug_name = None
    drug_pdb_text = None
    for pid, name in DRUG_COCRYSTALS.get(mutation.gene.upper(), [])[:1]:
        text = await _fetch_rcsb_pdb(pid, client)
        if text:
            drug_pdb_id, drug_name, drug_pdb_text = pid, name, text
            break

    view = MoleculeView(
        gene=mutation.gene,
        mutation_label=mutation.label,
        mutation_position=mut_window_pos,
        wt_pdb_text=wt_pdb,
        mut_pdb_text=mut_pdb,
        fold_method=method,  # type: ignore[arg-type]
        drug_complex_pdb_id=drug_pdb_id,
        drug_name=drug_name,
        drug_complex_pdb_text=drug_pdb_text,
    )
    await emit(
        EventKind.MOLECULE_READY,
        f"🧬 {mutation.full_label} folded ({method})"
        + (f" · co-crystal {drug_pdb_id}/{drug_name}" if drug_pdb_id else ""),
        {"view": view.model_dump()},
    )
    if drug_pdb_id:
        await emit(
            EventKind.DRUG_COMPLEX_READY,
            f"💊 {mutation.gene} ↔ {drug_name} co-crystal ({drug_pdb_id})",
            {"gene": mutation.gene, "pdb_id": drug_pdb_id, "drug": drug_name},
        )
    return view


async def build_landscape(mutations: list[Mutation]) -> list[MoleculeView]:
    """Build views for the top driver mutations (priority genes first, capped at 4)."""
    ranked = sorted(
        mutations,
        key=lambda m: (m.gene.upper() not in PRIORITY_GENES, m.gene),
    )
    chosen = ranked[:4]
    views: list[MoleculeView] = []
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(build_molecule_view(m, client) for m in chosen),
            return_exceptions=True,
        )
    for r in results:
        if isinstance(r, MoleculeView):
            views.append(r)
        elif isinstance(r, BaseException):
            await emit(EventKind.LOG, f"molecule build failed: {r}")
    return views
