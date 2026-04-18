"""3D structure prediction for peptides and pMHC complexes.

Strategy (in order of preference):
1. PANDORA — true pMHC homology modeling if installed and DB is built.
2. ESMFold via HuggingFace public endpoint — folds the peptide itself (fast, no GPU).
3. Template-based substitution — fall back to a reference pMHC PDB with annotation.

All results cached to ~/.cache/neoantigen/structures/ keyed by peptide+allele.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Optional

import httpx

from ..models import StructurePose


def _cache_dir() -> Path:
    root = Path(os.environ.get("NEOANTIGEN_CACHE", Path.home() / ".cache" / "neoantigen"))
    path = root / "structures"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_key(peptide: str, allele: str) -> str:
    h = hashlib.sha1(f"{peptide}|{allele}".encode()).hexdigest()[:16]
    return h


# ─────────────────────────────────────────────────────────────
# ESMFold via public endpoint
# ─────────────────────────────────────────────────────────────

ESMFOLD_URL = "https://api.esmatlas.com/foldSequence/v1/pdb/"


async def _fold_esmfold(sequence: str, timeout: float = 60.0) -> Optional[str]:
    """Submit a sequence to the public ESMFold endpoint, return PDB text."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(ESMFOLD_URL, data=sequence, headers={"Content-Type": "text/plain"})
            if resp.status_code == 200 and resp.text.startswith("HEADER") or resp.text.lstrip().startswith("ATOM"):
                return resp.text
            return None
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────
# PANDORA wrapper
# ─────────────────────────────────────────────────────────────


def _pandora_available() -> bool:
    try:
        import PANDORA  # noqa: F401
        return True
    except Exception:
        return False


async def _dock_pandora(peptide: str, allele: str, out_dir: Path) -> Optional[str]:
    """Run PANDORA modeling. Returns PDB text if successful."""
    if not _pandora_available():
        return None
    try:
        from PANDORA import Target, Pandora, Database

        db = Database.load()

        def _run() -> Optional[str]:
            target = Target(id=f"target_{_cache_key(peptide, allele)}", allele_type=[allele], peptide=peptide, anchors=[2, len(peptide)])
            case = Pandora.Pandora(target, db)
            case.model(n_loop_models=10, output_dir=str(out_dir))
            # Find best model
            for pdb in out_dir.glob("*.BL*.pdb"):
                return pdb.read_text()
            return None

        return await asyncio.to_thread(_run)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# Template pMHC — a reference PDB stub for when nothing else works
# ─────────────────────────────────────────────────────────────

# Minimal ATOM records for a 9-mer alpha-helix peptide (rough geometry).
# Used as an absolute last-resort visualization placeholder.
def _minimal_pdb(peptide: str) -> str:
    AA_MAP = {
        "A": "ALA", "R": "ARG", "N": "ASN", "D": "ASP", "C": "CYS",
        "Q": "GLN", "E": "GLU", "G": "GLY", "H": "HIS", "I": "ILE",
        "L": "LEU", "K": "LYS", "M": "MET", "F": "PHE", "P": "PRO",
        "S": "SER", "T": "THR", "W": "TRP", "Y": "TYR", "V": "VAL",
    }
    lines = ["HEADER    PEPTIDE (placeholder — PANDORA/ESMFold unavailable)"]
    atom_no = 1
    for i, aa in enumerate(peptide, start=1):
        res = AA_MAP.get(aa.upper(), "GLY")
        # Place Cα along the x axis with 3.8 Å spacing (ideal α-helix step is ~1.5Å rise,
        # 3.8 for extended; this is a schematic, not physically accurate).
        x, y, z = i * 3.8, 0.0, 0.0
        lines.append(
            f"ATOM  {atom_no:>5} CA   {res} A{i:>4}    "
            f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00 20.00           C"
        )
        atom_no += 1
    lines.append("END")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────


async def dock_peptide(peptide: str, allele: str, mutation_label: str = "") -> StructurePose:
    """Return a StructurePose with PDB text. Tries PANDORA → ESMFold → template stub."""

    cache_file = _cache_dir() / f"{_cache_key(peptide, allele)}.pdb"
    method: str = "template"

    # 1. Check cache
    if cache_file.exists():
        pdb_text = cache_file.read_text()
        # Detect method from header
        head = pdb_text[:200].upper()
        if "PANDORA" in head:
            method = "pandora"
        elif "ESMFOLD" in head or "ESM" in head:
            method = "esmfold"
        return StructurePose(
            peptide_sequence=peptide,
            mutation_label=mutation_label,
            dla_allele=allele,
            pdb_path=str(cache_file),
            pdb_text=pdb_text,
            method=method,  # type: ignore[arg-type]
        )

    # 2. PANDORA
    pdb_text: Optional[str] = None
    if _pandora_available():
        work_dir = _cache_dir() / f"pandora_{_cache_key(peptide, allele)}"
        work_dir.mkdir(exist_ok=True)
        pdb_text = await _dock_pandora(peptide, allele, work_dir)
        if pdb_text:
            method = "pandora"

    # 3. ESMFold
    if pdb_text is None:
        pdb_text = await _fold_esmfold(peptide)
        if pdb_text:
            method = "esmfold"
            pdb_text = f"HEADER    ESMFOLD {peptide} (allele {allele})\n" + pdb_text

    # 4. Template stub
    if pdb_text is None:
        pdb_text = _minimal_pdb(peptide)
        method = "template"

    cache_file.write_text(pdb_text)

    return StructurePose(
        peptide_sequence=peptide,
        mutation_label=mutation_label,
        dla_allele=allele,
        pdb_path=str(cache_file),
        pdb_text=pdb_text,
        method=method,  # type: ignore[arg-type]
    )
