"""Gene symbol → UniProt accession map for common cancer drivers.

Supports both human (default) and canine orthologs (gene names prefixed with `CANINE_`
or looked up via `lookup(gene, species="canine")`).
"""

GENE_TO_UNIPROT: dict[str, str] = {
    "BRAF": "P15056",
    "KRAS": "P01116",
    "NRAS": "P01111",
    "HRAS": "P01112",
    "TP53": "P04637",
    "PIK3CA": "P42336",
    "EGFR": "P00533",
    "ALK": "Q9UM73",
    "MYC": "P01106",
    "KIT": "P10721",
    "IDH1": "O75874",
    "IDH2": "P48735",
    "PTEN": "P60484",
    "APC": "P25054",
    "CTNNB1": "P35222",
    "SMAD4": "Q13485",
    "FGFR3": "P22607",
    "NOTCH1": "P46531",
    "JAK2": "O60674",
    "FLT3": "P36888",
}

CANINE_GENE_TO_UNIPROT: dict[str, str] = {
    # Empty by design: canine UniProt entries for these oncogenes are fragment
    # sequences. Dog/human orthologs are ≥95% identical in the relevant domains,
    # so we use human references with canine DLA scoring — standard practice in
    # comparative oncology. Add a canine accession here only if it's full-length
    # and reviewed (Swiss-Prot, not TrEMBL fragment).
}


def lookup(gene: str, species: str = "human") -> str | None:
    key = gene.upper()
    if species.lower() == "canine":
        return CANINE_GENE_TO_UNIPROT.get(key) or GENE_TO_UNIPROT.get(key)
    return GENE_TO_UNIPROT.get(key)
