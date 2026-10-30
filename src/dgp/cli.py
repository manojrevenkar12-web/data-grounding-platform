"""dgp: the platform's command line, for producers, the platform team and its product manager."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
import yaml

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Data grounding platform.")
contract = typer.Typer(no_args_is_help=True, help="Data contracts: what producers run in their own CI.")
keys = typer.Typer(no_args_is_help=True, help="API keys.")
app.add_typer(contract, name="contract")
app.add_typer(keys, name="keys")


@app.command()
def run() -> None:
    """Build the world and warehouse, run production and the bets, write reports/, end with the gate."""
    from . import pipeline

    results = pipeline.run(log=typer.echo)
    _gate(results["gate"])


@app.command()
def gate() -> None:
    """Re-check the release gate against reports/results.json."""
    from . import pipeline, settings

    _gate(pipeline.gate(json.loads((settings.REPORTS / "results.json").read_text())))


def _gate(checks: list[dict]) -> None:
    for c in checks:
        typer.echo(f"{'pass' if c['passed'] else 'FAIL'}  {c['name']}: {c['value']} {c['op']} {c['bound']}")
    failed = [c for c in checks if not c["passed"]]
    typer.echo(f"{len(checks) - len(failed)}/{len(checks)} checks pass")
    if failed:
        raise typer.Exit(1)


@contract.command("validate")
def contract_validate(topic: str, file: Path, contracts_dir: Path | None = None) -> None:
    """Check a delivery file (JSON lines) against its topic's contract, as the platform will at the door."""
    from .platform import contracts

    c = contracts.load(topic, contracts_dir)
    rows = [json.loads(line) for line in file.read_text().splitlines() if line.strip()]
    v = contracts.validate(c, rows)
    typer.echo(f"{'accepted' if v.accepted else 'refused'}: {v.rows} rows")
    for p in v.problems:
        typer.echo(f"  - {p}")
    if not v.accepted:
        raise typer.Exit(1)


@contract.command("diff")
def contract_diff(old: Path, new: Path) -> None:
    """Is a contract change safe for consumers? Breaking changes need a new major version."""
    from .platform import contracts

    a, b = (yaml.safe_load(p.read_text()) for p in (old, new))
    problems = contracts.structural(b)
    out = contracts.compatibility(a, b)
    typer.echo(json.dumps({**out, "structural": problems}, indent=2))
    if problems or not out["allowed"]:
        raise typer.Exit(1)


@contract.command("lint")
def contract_lint(contracts_dir: Path | None = None) -> None:
    """Every contract in the repository has what the platform needs."""
    from .platform import contracts

    bad = {t: p for t, c in contracts.all_contracts(contracts_dir).items() if (p := contracts.structural(c))}
    for t, p in bad.items():
        typer.echo(f"{t}: {'; '.join(p)}")
    typer.echo(f"{len(contracts.all_contracts(contracts_dir)) - len(bad)} contracts ok")
    if bad:
        raise typer.Exit(1)


@keys.command("issue")
def keys_issue(account_id: str, plan: str = typer.Option("team")) -> None:
    """Issue an API key (shown once)."""
    from . import settings
    from .service.keys import Keys

    if plan not in settings.load("platform")["plans"]:
        typer.echo(f"unknown plan {plan}", err=True)
        raise typer.Exit(2)
    typer.echo(Keys(settings.BUILD / "keys.json").issue(account_id, plan))


@app.command()
def ask(question: str, plan: str = typer.Option("enterprise"), as_of: str | None = None) -> None:
    """Answer a question the way an MCP client would: search, fetch, cite."""
    from datetime import datetime

    from .platform.catalog import Catalog
    from .platform.grounding import Account, Grounding

    g = Grounding(Catalog.load())
    acc = Account("cli", plan)
    now = datetime.now()
    hits = g.search(acc, question, now)
    if not hits["results"]:
        typer.echo("No statistic matches; the platform does not guess.")
        raise typer.Exit(1)
    top = hits["results"][0]
    years = [int(y) for y in g.c.parse(question)["years"]] or [None]
    out = g.get(acc, top["stat_id"], years[0], now, datetime.fromisoformat(as_of) if as_of else None)
    typer.echo(json.dumps(out, indent=2, default=str))


@app.command()
def heldout(name: str) -> None:
    """Score a blind question set through today's platform and the planned one (first run recorded once)."""
    from . import settings
    from .evals import heldout as h

    results = json.loads((settings.REPORTS / "results.json").read_text())
    out = h.run(name, {"today": {}, "plan": results["plan"]["flags"]}, results["glossary"])
    for config, c in out["configs"].items():
        typer.echo(
            f"{name} ({out['status']}) {config}: {c['right']}/{out['cases']} right"
            + (" — first run recorded" if out.get("first_run") else "")
        )


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8780) -> None:
    """The grounding API."""
    import uvicorn

    from .service.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


@app.command("serve-mcp")
def serve_mcp(http: bool = typer.Option(False), port: int = 8781) -> None:
    """The MCP server (stdio by default; DGP_API_KEY decides the account)."""
    from .service.mcp_server import from_env

    server = from_env()
    if http:
        server.run(transport="streamable-http", port=port)
    else:
        server.run()


@app.command("export-web")
def export_web() -> None:
    """The dashboard's data, to web/public/data."""
    from .product import export

    typer.echo("wrote " + ", ".join(export.run()))


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
