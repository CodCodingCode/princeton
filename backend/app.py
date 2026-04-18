import asyncio
import io
from pathlib import Path

import httpx
import plotly.express as px
import plotly.graph_objects as go
import py3Dmol
import streamlit as st
import streamlit.components.v1 as components

from neoantigen.external.clinicaltrials import search_trials
from neoantigen.external.dgidb import search_drugs
from neoantigen.models import PipelineResult
from neoantigen.pipeline.construct import build_construct
from neoantigen.pipeline.filters import filter_candidates
from neoantigen.pipeline.parser import parse_tsv
from neoantigen.pipeline.peptides import generate_peptides
from neoantigen.pipeline.protein import apply_mutation, fetch_protein
from neoantigen.pipeline.scoring import build_scorer

st.set_page_config(page_title="NeoVax", page_icon="🧬", layout="wide")

SAMPLE = Path(__file__).parent / "sample_data" / "braf_v600e.tsv"

# ── sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.title("NeoVax")
st.sidebar.caption("Personalized cancer vaccine pipeline")

scorer_choice = st.sidebar.radio("Scorer", ["heuristic", "mhcflurry"], index=0)
allele = st.sidebar.text_input("MHC allele", value="HLA-A*02:01")
top_n = st.sidebar.slider("Top N candidates", 3, 30, 15)
max_nm = st.sidebar.slider("Affinity cutoff (nM)", 100, 10000, 500, step=100)
with_apis = st.sidebar.checkbox("Query ClinicalTrials.gov + DGIdb", value=False)

st.sidebar.divider()
input_mode = st.sidebar.radio("Input", ["Upload file", "Use demo data"])

# ── input ────────────────────────────────────────────────────────────────────

mutations = None
if input_mode == "Upload file":
    uploaded = st.sidebar.file_uploader("Upload VCF or TSV", type=["vcf", "tsv", "txt", "csv"])
    if uploaded is not None:
        tmp = Path("/tmp/neoantigen_upload" + Path(uploaded.name).suffix)
        tmp.write_bytes(uploaded.read())
        from neoantigen.pipeline.parser import parse
        mutations = parse(tmp)
else:
    if SAMPLE.exists():
        mutations = parse_tsv(SAMPLE)
    else:
        st.error("Demo sample not found")

if mutations is None:
    st.info("Upload a mutation file or select demo data in the sidebar to begin.")
    st.stop()

# ── run pipeline ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Running pipeline...")
def run_pipeline(_mutation_tuples, scorer_name, _allele, _top_n, _max_nm, _with_apis):
    from neoantigen.models import Mutation
    _mutations = [Mutation(gene=g, ref_aa=r, position=p, alt_aa=a) for g, r, p, a in _mutation_tuples]
    scorer = build_scorer(scorer_name, _allele)
    all_peptides = []
    reference_by_gene = {}

    for m in _mutations:
        if m.gene not in reference_by_gene:
            reference_by_gene[m.gene] = fetch_protein(m.gene)
        ref = reference_by_gene[m.gene]
        mutant = apply_mutation(ref, m)
        peps = generate_peptides(mutant, m)
        all_peptides.extend(peps)

    scorer.score(all_peptides)

    filtered = []
    for m in _mutations:
        mpeps = [p for p in all_peptides if p.mutation.full_label == m.full_label]
        ref = reference_by_gene[m.gene]
        filtered.extend(filter_candidates(mpeps, ref, max_nm=_max_nm))

    filtered.sort(key=lambda p: p.score_nm or float("inf"))
    from neoantigen.models import Candidate
    candidates = [Candidate(peptide=p, rank=i + 1) for i, p in enumerate(filtered[:_top_n])]
    construct = build_construct(candidates) if candidates else None

    drugs, trials = [], []
    if _with_apis:
        async def _fetch():
            genes = sorted({m.gene for m in _mutations})
            async with httpx.AsyncClient() as client:
                d = await asyncio.gather(*[search_drugs(client, g) for g in genes])
                t = await asyncio.gather(*[search_trials(client, g) for g in genes])
            return [x for sub in d for x in sub], [x for sub in t for x in sub]
        drugs, trials = asyncio.run(_fetch())

    return PipelineResult(
        mutations=_mutations,
        candidates=candidates,
        drugs=drugs,
        trials=trials,
        vaccine=construct,
    ), all_peptides, filtered


mut_tuples = tuple((m.gene, m.ref_aa, m.position, m.alt_aa) for m in mutations)
result, all_peptides, filtered = run_pipeline(
    mut_tuples, scorer_choice, allele, top_n, max_nm, with_apis,
)

# reconstruct Mutation objects from tuples (st.cache_data serializes)
from neoantigen.models import Mutation
mutations = [Mutation(gene=g, ref_aa=r, position=p, alt_aa=a) for g, r, p, a in mut_tuples]

# ── header ───────────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)
col1.metric("Mutations", len(mutations))
col2.metric("Peptides scored", len(all_peptides))
col3.metric("Passed filter", len(filtered))
col4.metric("In construct", len(result.candidates))

# ── mutations table ──────────────────────────────────────────────────────────

st.header("Input mutations")
mut_data = [{"Gene": m.gene, "Mutation": f"{m.ref_aa}{m.position}{m.alt_aa}"} for m in mutations]
st.dataframe(mut_data, use_container_width=True, hide_index=True)

# ── candidate leaderboard ────────────────────────────────────────────────────

st.header("Ranked vaccine candidates")

if result.candidates:
    cand_data = []
    for c in result.candidates:
        cand_data.append({
            "Rank": c.rank,
            "Peptide": c.peptide.sequence,
            "Length": c.peptide.length,
            "Gene": c.peptide.mutation.gene,
            "Mutation": c.peptide.mutation.label,
            "Score (nM)": round(c.peptide.score_nm, 2) if c.peptide.score_nm else None,
        })
    st.dataframe(cand_data, use_container_width=True, hide_index=True)

    # bar chart
    fig = px.bar(
        cand_data,
        x="Peptide",
        y="Score (nM)",
        color="Gene",
        title="Binding affinity by candidate (lower = stronger)",
        labels={"Score (nM)": "Predicted IC50 (nM)"},
    )
    fig.update_layout(xaxis_tickangle=-45, height=400)
    st.plotly_chart(fig, use_container_width=True)

    # scatter: length vs score
    fig2 = px.scatter(
        cand_data,
        x="Length",
        y="Score (nM)",
        color="Gene",
        size=[8] * len(cand_data),
        hover_data=["Peptide", "Mutation"],
        title="Peptide length vs binding affinity",
    )
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.warning("No candidates survived filtering. Try raising the nM cutoff.")

# ── 3D protein structures ────────────────────────────────────────────────────

st.header("3D protein structures")
st.caption("AlphaFold-predicted structures — mutation sites highlighted in red")

ALPHAFOLD_API = "https://alphafold.ebi.ac.uk/api/prediction/{accession}"

from neoantigen.genes import GENE_TO_UNIPROT

gene_mutations: dict[str, list] = {}
for m in mutations:
    gene_mutations.setdefault(m.gene, []).append(m)

structure_genes = [g for g in gene_mutations if g in GENE_TO_UNIPROT]

if structure_genes:
    tabs = st.tabs(structure_genes)
    for tab, gene in zip(tabs, structure_genes):
        with tab:
            accession = GENE_TO_UNIPROT[gene]
            cache_path = Path.home() / ".cache" / "neoantigen" / "structures" / f"{accession}.pdb"
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            pdb_data = None
            if cache_path.exists():
                pdb_data = cache_path.read_text()
            else:
                try:
                    api_resp = httpx.get(
                        ALPHAFOLD_API.format(accession=accession),
                        timeout=15.0,
                        follow_redirects=True,
                    )
                    api_resp.raise_for_status()
                    pdb_url = api_resp.json()[0]["pdbUrl"]
                    pdb_resp = httpx.get(pdb_url, timeout=30.0, follow_redirects=True)
                    pdb_resp.raise_for_status()
                    pdb_data = pdb_resp.text
                    cache_path.write_text(pdb_data)
                except (httpx.HTTPError, KeyError, IndexError) as e:
                    st.warning(f"Could not fetch AlphaFold structure for {gene} ({accession}): {e}")

            if pdb_data:
                mut_positions = [m.position for m in gene_mutations[gene]]
                mut_labels = [m.label for m in gene_mutations[gene]]

                viewer = py3Dmol.view(width=700, height=500)
                viewer.addModel(pdb_data, "pdb")

                viewer.setStyle({"cartoon": {"color": "spectrum"}})

                for pos in mut_positions:
                    viewer.addStyle(
                        {"resi": pos},
                        {"cartoon": {"color": "red"}, "stick": {"color": "red", "radius": 0.3}},
                    )

                viewer.addStyle(
                    {"resi": mut_positions},
                    {"stick": {"color": "red", "radius": 0.3}},
                )

                for pos, label in zip(mut_positions, mut_labels):
                    viewer.addLabel(
                        label,
                        {
                            "fontSize": 14,
                            "fontColor": "white",
                            "backgroundColor": "rgba(200,0,0,0.8)",
                            "position": {"resi": pos},
                        },
                        {"resi": pos},
                    )

                viewer.zoomTo({"resi": mut_positions})
                viewer.spin(True)
                html = viewer._make_html()
                components.html(html, height=520, width=720, scrolling=False)

                st.caption(
                    f"**{gene}** (UniProt {accession}) — "
                    f"mutations: {', '.join(mut_labels)} — "
                    f"colored by rainbow spectrum, mutation sites in red with sticks"
                )
else:
    st.info("No AlphaFold structures available for the input genes.")

# ── score distribution ───────────────────────────────────────────────────────

st.header("Score distribution (all peptides)")
scores = [p.score_nm for p in all_peptides if p.score_nm is not None]
if scores:
    fig3 = px.histogram(
        x=scores,
        nbins=50,
        title="Binding affinity distribution",
        labels={"x": "Predicted IC50 (nM)", "y": "Count"},
    )
    fig3.add_vline(x=max_nm, line_dash="dash", line_color="red", annotation_text=f"Cutoff: {max_nm} nM")
    st.plotly_chart(fig3, use_container_width=True)

# ── construct ────────────────────────────────────────────────────────────────

st.header("mRNA vaccine construct")
if result.vaccine:
    v = result.vaccine
    c1, c2, c3 = st.columns(3)
    c1.metric("Nucleotide length", f"{v.length_bp} bp")
    c2.metric("Epitopes", len(v.epitopes))
    c3.metric("Est. synthesis cost", f"${v.estimated_cost_usd}")

    with st.expander("Amino acid sequence"):
        st.code(v.amino_acid_sequence, language=None)
    with st.expander("Nucleotide sequence"):
        st.code(v.nucleotide_sequence, language=None)

    # FASTA download
    genes_str = "_".join(sorted({m.gene for m in mutations}))
    header = f">neoantigen_vaccine|{genes_str}|{len(v.epitopes)}epitopes"
    nt = v.nucleotide_sequence
    fasta_lines = [header] + [nt[i:i + 60] for i in range(0, len(nt), 60)]
    fasta_content = "\n".join(fasta_lines) + "\n"

    st.download_button(
        "Download FASTA",
        data=fasta_content,
        file_name="vaccine.fasta",
        mime="text/plain",
    )

    # cost breakdown
    st.subheader("Synthesis cost estimate")
    cost_data = [
        {"Provider": "Twist Bioscience (fragments)", "Cost/bp": "$0.07", "Total": f"${round(v.length_bp * 0.07, 2)}"},
        {"Provider": "Twist Bioscience (clonal)", "Cost/bp": "$0.09", "Total": f"${round(v.length_bp * 0.09, 2)}"},
        {"Provider": "IDT gBlocks", "Cost/bp": "~$0.10", "Total": f"~${round(v.length_bp * 0.10, 2)}"},
    ]
    st.dataframe(cost_data, use_container_width=True, hide_index=True)
else:
    st.warning("No construct — no candidates passed filtering.")

# ── drug interactions ────────────────────────────────────────────────────────

if result.drugs:
    st.header("Drug-gene interactions (DGIdb)")
    seen = set()
    drug_data = []
    for d in result.drugs:
        key = (d.gene, d.drug_name)
        if key in seen:
            continue
        seen.add(key)
        drug_data.append({
            "Gene": d.gene,
            "Drug": d.drug_name,
            "Interaction": ", ".join(d.interaction_types) or "—",
            "Sources": ", ".join(d.sources[:3]) or "—",
        })
    st.dataframe(drug_data, use_container_width=True, hide_index=True)

# ── clinical trials ──────────────────────────────────────────────────────────

if result.trials:
    st.header("Clinical trials (ClinicalTrials.gov)")
    trial_data = []
    for t in result.trials[:15]:
        trial_data.append({
            "NCT ID": t.nct_id,
            "Phase": t.phase or "—",
            "Status": t.status,
            "Title": t.title[:100],
            "Link": t.url,
        })
    st.dataframe(
        trial_data,
        use_container_width=True,
        hide_index=True,
        column_config={"Link": st.column_config.LinkColumn("Link")},
    )

# ── JSON export ──────────────────────────────────────────────────────────────

st.divider()
st.download_button(
    "Download full results (JSON)",
    data=result.model_dump_json(indent=2),
    file_name="vaccine_results.json",
    mime="application/json",
)
