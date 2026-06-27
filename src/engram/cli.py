"""Engram command-line interface (Typer).

Commands grow across build phases:
  engram serve       — run the FastAPI server
  engram dashboard   — run the Streamlit dashboard
  engram migrate     — apply Alembic migrations
  engram bootstrap   — seed the bootstrap tenant + Qdrant collection
  engram capture     — record a real troubleshooting session and ingest it
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich import print as rprint

from engram.config import get_settings

app = typer.Typer(
    add_completion=False,
    help="Engram — network-specific incident memory.",
    no_args_is_help=True,
)


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Override API_HOST."),
    port: int | None = typer.Option(None, help="Override API_PORT."),
    reload: bool = typer.Option(False, help="Auto-reload (dev)."),
) -> None:
    """Run the FastAPI server."""
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "engram.main:create_app",
        factory=True,
        host=host or s.api_host,
        port=port or s.api_port,
        reload=reload,
    )


@app.command()
def dashboard(
    port: int = typer.Option(8501, help="Streamlit port."),
) -> None:
    """Run the Streamlit dashboard (talks to the API, not the DB)."""
    app_path = Path(__file__).resolve().parents[2] / "dashboard" / "app.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)],
        check=True,
    )


@app.command()
def migrate() -> None:
    """Apply Alembic migrations (alembic upgrade head)."""
    subprocess.run(["alembic", "upgrade", "head"], check=True)


@app.command()
def bootstrap() -> None:
    """Seed the bootstrap tenant/API key and ensure the Qdrant collection exists."""
    from engram.storage.bootstrap import bootstrap_all

    created = bootstrap_all()
    rprint(f"[green]Bootstrap complete[/green]: {created}")


@app.command()
def capture(
    host: str = typer.Option(..., help="Device hostname/IP to SSH into."),
    device_type: str = typer.Option(
        "linux", help="Netmiko device_type (e.g. cisco_ios, arista_eos, linux)."
    ),
    network_id: str | None = typer.Option(None, help="Tenant; defaults to bootstrap network."),
    from_file: Path | None = typer.Option(
        None, "--from-file", help="Ingest a saved transcript instead of connecting live."
    ),
    api_url: str = typer.Option("http://localhost:8000", help="Engram API base URL."),
    api_key: str | None = typer.Option(None, help="X-API-Key; defaults to bootstrap key."),
    draft_out: Path | None = typer.Option(
        None, help="Write the assembled incident draft to JSON instead of POSTing."
    ),
) -> None:
    """Record a real troubleshooting session and ingest it as an incident."""
    from engram.capture.cli_capture import run_capture

    run_capture(
        host=host,
        device_type=device_type,
        network_id=network_id,
        from_file=from_file,
        api_url=api_url,
        api_key=api_key,
        draft_out=draft_out,
    )


if __name__ == "__main__":
    app()
