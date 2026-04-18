"""Gene symbol → UniProt accession map for melanoma + pan-cancer drivers."""

GENE_TO_UNIPROT: dict[str, str] = {
    # Melanoma drivers (priority — these light up Panel 2 + drug co-crystals)
    "BRAF": "P15056",
    "NRAS": "P01111",
    "KIT": "P10721",
    "NF1": "P21359",
    "CDKN2A": "P42771",
    "TP53": "P04637",
    "PTEN": "P60484",
    "MAP2K1": "Q02750",
    "MAP2K2": "P36507",
    "MITF": "O75030",
    "TERT": "O14746",
    "GNAQ": "P50148",
    "GNA11": "P29992",
    # Other common drivers (kept for general use)
    "KRAS": "P01116",
    "HRAS": "P01112",
    "PIK3CA": "P42336",
    "EGFR": "P00533",
    "ALK": "Q9UM73",
    "MYC": "P01106",
    "IDH1": "O75874",
    "IDH2": "P48735",
    "APC": "P25054",
    "CTNNB1": "P35222",
    "SMAD4": "Q13485",
    "FGFR3": "P22607",
    "NOTCH1": "P46531",
    "JAK2": "O60674",
    "FLT3": "P36888",
}


def lookup(gene: str) -> str | None:
    return GENE_TO_UNIPROT.get(gene.upper())
