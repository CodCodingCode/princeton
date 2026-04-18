"""Terminal interface for NeoVax — currently just boots the FastAPI server."""

from __future__ import annotations

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    help="NeoVax — pathology PDF → NCCN railway → Kimi chat → oncologist report + trial-site map.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


@app.command("serve")
def serve_command(
    host: Annotated[str, typer.Option(help="Bind host")] = "0.0.0.0",
    port: Annotated[int, typer.Option(help="Bind port")] = 8000,
    reload: Annotated[bool, typer.Option(help="Enable autoreload for dev")] = False,
) -> None:
    """Boot the NeoVax FastAPI + SSE backend."""
    import uvicorn

    uvicorn.run(
        "neoantigen.web.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    app()
