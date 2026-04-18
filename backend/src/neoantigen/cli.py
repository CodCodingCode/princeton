"""Terminal interface for the neoantigen vaccine pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

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
    help="Personalized cancer vaccine pipeline — tumor mutations in, mRNA vaccine out.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()

SAMPLE_BRAF = Path(__file__).resolve().parent.parent.parent / "sample_data" / "braf_v600e.tsv"


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


def _render_drugs(result: PipelineResult) -> Table | None:
    if not result.drugs:
        return None
    table = Table(title="Drug-gene interactions (DGIdb)", title_style="bold white")
    table.add_column("Gene", style="magenta")
    table.add_column("Drug", style="bold yellow")
    table.add_column("Interaction")
    table.add_column("Sources", style="dim")
    seen: set[tuple[str, str]] = set()
    for d in result.drugs:
        key = (d.gene, d.drug_name)
        if key in seen:
            continue
        seen.add(key)
        table.add_row(
            d.gene,
            d.drug_name,
            ", ".join(d.interaction_types) or "—",
            ", ".join(d.sources[:3]) or "—",
        )
    return table


def _render_trials(result: PipelineResult) -> Table | None:
    if not result.trials:
        return None
    table = Table(title="Clinical trials (ClinicalTrials.gov)", title_style="bold white")
    table.add_column("NCT ID", style="bold cyan")
    table.add_column("Phase", style="yellow")
    table.add_column("Status")
    table.add_column("Title")
    for t in result.trials[:10]:
        table.add_row(t.nct_id, t.phase or "—", t.status or "—", t.title[:80])
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
    summary.append("(at $0.07/bp, Twist fragments)\n", style="dim")
    summary.append("Linker: ", style="dim")
    summary.append(f"{c.linker}\n\n")
    summary.append("Amino acid sequence:\n", style="dim")
    summary.append(c.amino_acid_sequence + "\n\n", style="bold yellow")
    summary.append("Nucleotide sequence (first 120 bp):\n", style="dim")
    summary.append(c.nucleotide_sequence[:120] + "..." if len(c.nucleotide_sequence) > 120 else c.nucleotide_sequence, style="green")
    return Panel(summary, title="mRNA vaccine construct", border_style="green")


def _write_fasta(result: PipelineResult, path: Path) -> None:
    if not result.vaccine:
        return
    genes = "_".join(sorted({m.gene for m in result.mutations}))
    header = f">neoantigen_vaccine|{genes}|{len(result.vaccine.epitopes)}epitopes"
    nt = result.vaccine.nucleotide_sequence
    lines = [header] + [nt[i : i + 60] for i in range(0, len(nt), 60)]
    path.write_text("\n".join(lines) + "\n")


def _write_json(result: PipelineResult, path: Path) -> None:
    path.write_text(json.dumps(result.model_dump(), indent=2))


def _render_all(result: PipelineResult) -> None:
    console.print(_render_mutations(result))
    console.print(_render_candidates(result))
    for panel in [_render_drugs(result), _render_trials(result), _render_construct(result)]:
        if panel is not None:
            console.print(panel)


@app.command("run")
def run_command(
    input_path: Annotated[Path, typer.Argument(help="VCF (SnpEff-annotated) or gene/mutation TSV")],
    output: Annotated[Path, typer.Option("--output", "-o", help="FASTA output path")] = Path("vaccine.fasta"),
    json_output: Annotated[Path | None, typer.Option("--json", help="Optional JSON results dump")] = None,
    top: Annotated[int, typer.Option("--top", help="Number of top peptides to include in construct")] = 15,
    max_nm: Annotated[float, typer.Option("--max-nm", help="Affinity cutoff in nM")] = 500.0,
    allele: Annotated[str, typer.Option("--allele", help="MHC allele")] = "HLA-A*02:01",
    mhcflurry: Annotated[bool, typer.Option("--mhcflurry", help="Use MHCflurry ML model (requires install)")] = False,
    with_apis: Annotated[bool, typer.Option("--with-apis", help="Query ClinicalTrials.gov + DGIdb")] = False,
) -> None:
    """Run the pipeline on a VCF or TSV mutation file."""
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
        with_apis=with_apis,
    )

    result = run(mutations, config, console=console)
    _render_all(result)

    if result.vaccine:
        _write_fasta(result, output)
        console.print(f"[bold green]→ Wrote FASTA:[/bold green] {output}")
    else:
        console.print("[yellow]No candidates survived filtering — no construct written.[/yellow]")

    if json_output:
        _write_json(result, json_output)
        console.print(f"[bold green]→ Wrote JSON:[/bold green] {json_output}")


@app.command("demo")
def demo_command(
    with_apis: Annotated[bool, typer.Option("--with-apis", help="Also query ClinicalTrials.gov + DGIdb")] = False,
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
        with_apis=with_apis,
    )


@app.command("fetch-gene")
def fetch_gene_command(gene: str, force: bool = typer.Option(False, "--force")) -> None:
    """Prefetch and cache a reference protein from UniProt."""
    seq = fetch_protein(gene, force=force)
    console.print(f"[green]{gene}[/green]: {len(seq)} aa cached")


@app.command("agent-demo")
def agent_demo_command(
    pdf: Annotated[Path, typer.Option("--pdf", help="Pathology PDF")] = Path("sample_data/luna_pathology.pdf"),
    vcf: Annotated[Path, typer.Option("--vcf", help="Tumor VCF/TSV")] = Path("sample_data/luna_tumor.vcf"),
    output: Annotated[Path, typer.Option("--output", help="Write case JSON to this path")] = Path("out/case_package.json"),
) -> None:
    """Headless agent run — drives the full orchestrator end to end, writes JSON at the end."""
    import asyncio
    import json

    from .agent import EventBus, EventKind, build_case_file
    from .agent.orchestrator import CaseOrchestrator

    if not pdf.exists():
        console.print(f"[red]PDF not found:[/red] {pdf}")
        raise typer.Exit(1)
    if not vcf.exists():
        console.print(f"[red]VCF not found:[/red] {vcf}")
        raise typer.Exit(1)

    events: list = []

    async def run() -> None:
        bus = EventBus()
        orch = CaseOrchestrator(vcf_path=vcf, pdf_path=pdf, bus=bus)

        async def drain() -> None:
            async for ev in bus.stream():
                events.append(ev)
                prefix = {
                    EventKind.TOOL_START: "[cyan]▶[/cyan]",
                    EventKind.TOOL_RESULT: "[green]✓[/green]",
                    EventKind.TOOL_ERROR: "[red]✗[/red]",
                    EventKind.STRUCTURE_READY: "[magenta]🔭[/magenta]",
                    EventKind.EMAIL_DRAFTED: "[yellow]📧[/yellow]",
                    EventKind.DONE: "[bold green]🎉[/bold green]",
                }.get(ev.kind, "·")
                console.print(f"{prefix} {ev.label}")

        drain_task = asyncio.create_task(drain())
        try:
            await orch.run()
        finally:
            await drain_task

    asyncio.run(run())

    case = build_case_file(events)
    output.parent.mkdir(parents=True, exist_ok=True)
    if case:
        output.write_text(json.dumps(case.model_dump(), indent=2, default=str))
        console.print(f"[bold green]→ Wrote case package:[/bold green] {output}")
    else:
        console.print("[yellow]No case package reconstructed (incomplete run).[/yellow]")


if __name__ == "__main__":
    app()
