"""Terminal interface for the melanoma copilot pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import PipelineResult
from .pipeline.parser import parse
from .pipeline.protein import fetch_protein
from .pipeline.runner import RunConfig, run
from .pipeline.scoring import build_scorer

app = typer.Typer(
    help="Melanoma oncologist copilot — VCF in, NCCN-walked treatment plan + vaccine candidates out.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "sample_data"
SAMPLE_BRAF = SAMPLE_DIR / "braf_v600e.tsv"
SAMPLE_MELANOMA_VCF = SAMPLE_DIR / "tcga_skcm_demo.vcf"
SAMPLE_MELANOMA_SLIDE = SAMPLE_DIR / "tcga_skcm_demo_slide.jpg"
TCGA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "tcga_skcm"
TCGA_DEMO_SLIDE = TCGA_DIR / "demo_slide.jpg"


def _render_mutations(result: PipelineResult) -> Table:
    table = Table(title="Input mutations", title_style="bold white")
    table.add_column("Gene", style="magenta")
    table.add_column("Mutation", style="bold")
    for m in result.mutations:
        table.add_row(m.gene, m.label)
    return table


def _render_candidates(result: PipelineResult) -> Table:
    table = Table(title="Ranked vaccine candidates", title_style="bold white")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Peptide", style="bold green")
    table.add_column("Len", justify="right")
    table.add_column("Gene/Mut", style="magenta")
    table.add_column("Score (nM)", justify="right", style="cyan")
    for c in result.candidates:
        score = f"{c.peptide.score_nm:.2f}" if c.peptide.score_nm is not None else "—"
        table.add_row(
            str(c.rank),
            c.peptide.sequence,
            str(c.peptide.length),
            c.peptide.mutation.full_label,
            score,
        )
    return table


def _render_construct(result: PipelineResult) -> Panel | None:
    if not result.vaccine:
        return None
    c = result.vaccine
    summary = Text()
    summary.append("Epitopes: ", style="dim")
    summary.append(f"{len(c.epitopes)}\n")
    summary.append("Protein length: ", style="dim")
    summary.append(f"{len(c.amino_acid_sequence)} aa\n")
    summary.append("Nucleotide length: ", style="dim")
    summary.append(f"{c.length_bp} bp\n")
    summary.append("Est. synthesis cost: ", style="dim")
    summary.append(f"${c.estimated_cost_usd} ", style="bold green")
    summary.append("(at $0.07/bp)\n", style="dim")
    summary.append("Linker: ", style="dim")
    summary.append(f"{c.linker}\n\n")
    summary.append("Amino acid sequence:\n", style="dim")
    summary.append(c.amino_acid_sequence + "\n", style="bold yellow")
    return Panel(summary, title="mRNA vaccine construct", border_style="green")


@app.command("run")
def run_command(
    input_path: Annotated[Path, typer.Argument(help="VCF (SnpEff-annotated) or gene/mutation TSV")],
    output: Annotated[Path, typer.Option("--output", "-o", help="FASTA output path")] = Path("vaccine.fasta"),
    json_output: Annotated[Path | None, typer.Option("--json", help="Optional JSON results dump")] = None,
    top: Annotated[int, typer.Option("--top", help="Number of top peptides to include in construct")] = 15,
    max_nm: Annotated[float, typer.Option("--max-nm", help="Affinity cutoff in nM")] = 500.0,
    allele: Annotated[str, typer.Option("--allele", help="MHC allele")] = "HLA-A*02:01",
    mhcflurry: Annotated[bool, typer.Option("--mhcflurry", help="Use MHCflurry ML model (requires install)")] = False,
) -> None:
    """Run the vaccine pipeline on a VCF or TSV mutation file."""
    if not input_path.exists():
        console.print(f"[red]Input not found:[/red] {input_path}")
        raise typer.Exit(code=1)

    mutations = parse(input_path)
    if not mutations:
        console.print("[red]No mutations parsed from input.[/red]")
        raise typer.Exit(code=1)

    scorer_name = "mhcflurry" if mhcflurry else "heuristic"
    config = RunConfig(
        scorer=build_scorer(scorer_name, allele),
        top_n=top,
        max_nm=max_nm,
    )

    result = run(mutations, config, console=console)
    console.print(_render_mutations(result))
    console.print(_render_candidates(result))
    panel = _render_construct(result)
    if panel:
        console.print(panel)

    if result.vaccine:
        genes = "_".join(sorted({m.gene for m in result.mutations}))
        header = f">neoantigen_vaccine|{genes}|{len(result.vaccine.epitopes)}epitopes"
        nt = result.vaccine.nucleotide_sequence
        lines = [header] + [nt[i:i + 60] for i in range(0, len(nt), 60)]
        output.write_text("\n".join(lines) + "\n")
        console.print(f"[bold green]→ Wrote FASTA:[/bold green] {output}")

    if json_output:
        json_output.write_text(json.dumps(result.model_dump(), indent=2))
        console.print(f"[bold green]→ Wrote JSON:[/bold green] {json_output}")


@app.command("demo")
def demo_command(
    mhcflurry: Annotated[bool, typer.Option("--mhcflurry", help="Use MHCflurry ML model")] = False,
) -> None:
    """Run the bundled BRAF V600E demo input."""
    if not SAMPLE_BRAF.exists():
        console.print(f"[red]Bundled sample missing:[/red] {SAMPLE_BRAF}")
        raise typer.Exit(code=1)
    run_command(
        input_path=SAMPLE_BRAF,
        output=Path("vaccine.fasta"),
        json_output=Path("vaccine.json"),
        top=15,
        max_nm=500.0,
        allele="HLA-A*02:01",
        mhcflurry=mhcflurry,
    )


@app.command("fetch-gene")
def fetch_gene_command(gene: str, force: bool = typer.Option(False, "--force")) -> None:
    """Prefetch and cache a reference protein from UniProt."""
    seq = fetch_protein(gene, force=force)
    console.print(f"[green]{gene}[/green]: {len(seq)} aa cached")


@app.command("melanoma-demo")
def melanoma_demo_command(
    slide: Annotated[Path | None, typer.Option("--slide", help="Pathology slide image")] = None,
    vcf: Annotated[Path | None, typer.Option("--vcf", help="Tumour VCF")] = None,
    tcga_patient: Annotated[str | None, typer.Option("--tcga-patient", help="TCGA submitter id (overrides --vcf)")] = None,
    output: Annotated[Path, typer.Option("--output", help="Where to write the case JSON")] = Path("out/melanoma_case.json"),
) -> None:
    """End-to-end melanoma agent: VLM pathology → NCCN walk → molecular landscape → vaccine → twin cohort.

    If the TCGA-SKCM cohort has been pre-built (``backend/scripts/fetch_tcga_skcm.py``)
    the demo defaults to running on the bundled BRAF V600E demo patient. Otherwise
    it falls back to the synthetic VCF + sample slide.
    """
    import asyncio

    from .agent import EventBus, EventKind
    from .agent.melanoma_orchestrator import MelanomaOrchestrator
    from .cohort import has_cohort, demo_patient_id

    chosen_tcga: str | None = tcga_patient
    if chosen_tcga is None and has_cohort():
        chosen_tcga = demo_patient_id()
        if chosen_tcga:
            console.print(f"[cyan]→ using TCGA-SKCM demo patient[/cyan] {chosen_tcga}")

    chosen_slide = slide
    if chosen_slide is None:
        chosen_slide = TCGA_DEMO_SLIDE if TCGA_DEMO_SLIDE.exists() else SAMPLE_MELANOMA_SLIDE
    chosen_vcf = vcf if vcf is not None else SAMPLE_MELANOMA_VCF

    if chosen_tcga is None and not chosen_vcf.exists():
        console.print(f"[red]VCF not found:[/red] {chosen_vcf}")
        raise typer.Exit(1)
    if not chosen_slide.exists():
        console.print(f"[yellow]Slide not found:[/yellow] {chosen_slide} — VLM will fall back to placeholder.")

    async def runit():
        bus = EventBus()
        orch = MelanomaOrchestrator(
            slide_path=chosen_slide,
            vcf_path=chosen_vcf,
            bus=bus,
            tcga_patient_id=chosen_tcga,
        )

        async def drain():
            async for ev in bus.stream():
                prefix = {
                    EventKind.TOOL_START: "[cyan]▶[/cyan]",
                    EventKind.TOOL_RESULT: "[green]✓[/green]",
                    EventKind.TOOL_ERROR: "[red]✗[/red]",
                    EventKind.NCCN_NODE_VISITED: "[magenta]🩺[/magenta]",
                    EventKind.MOLECULE_READY: "[blue]🧬[/blue]",
                    EventKind.STRUCTURE_READY: "[magenta]🔭[/magenta]",
                    EventKind.RAG_CITATIONS: "[yellow]📚[/yellow]",
                    EventKind.COHORT_TWINS_READY: "[cyan]🧑‍🤝‍🧑[/cyan]",
                    EventKind.SURVIVAL_CURVE_READY: "[cyan]📈[/cyan]",
                    EventKind.DONE: "[bold green]🎉[/bold green]",
                }.get(ev.kind, "·")
                if ev.kind in {EventKind.THINKING_DELTA, EventKind.ANSWER_DELTA}:
                    continue
                console.print(f"{prefix} {ev.label}")

        drain_task = asyncio.create_task(drain())
        case = await orch.run()
        await drain_task
        return case

    case = asyncio.run(runit())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(case.model_dump(), indent=2, default=str))
    console.print(f"[bold green]→ Wrote case package:[/bold green] {output}")


if __name__ == "__main__":
    app()
