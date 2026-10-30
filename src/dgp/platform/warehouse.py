"""dbt over the warehouse: staging and marts (fct_values, fct_statistic_versions, dim_statistic) with
their tests. DuckDB locally; the same models run on Snowflake with a snowflake target.

dbt runs in its own process, as it would in the orchestrator, so it never holds the warehouse open
in the service's process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .. import settings


def build(path: Path | None = None, select: str | None = None) -> dict[str, Any]:
    env = {**os.environ, "DGP_WAREHOUSE": str(path or settings.warehouse()), "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    target = (path or settings.warehouse()).parent / "dbt-target"
    args = [
        sys.executable,
        "-c",
        "from dbt.cli.main import cli; cli()",
        "build",
        "--project-dir",
        str(settings.DBT),
        "--profiles-dir",
        str(settings.DBT),
        "--target-path",
        str(target),
        "--quiet",
    ]
    if select:
        args += ["--select", select]
    p = subprocess.run(args, env=env, capture_output=True, text=True, check=False)
    results = []
    run_results = target / "run_results.json"
    if run_results.exists():
        results = [
            {"node": r["unique_id"].split(".")[-1], "status": r["status"]}
            for r in json.loads(run_results.read_text())["results"]
        ]
    return {
        "success": p.returncode == 0,
        "results": results,
        "failed": [r for r in results if r["status"] not in ("success", "pass")],
        "log": (p.stdout + p.stderr)[-2000:] if p.returncode else "",
    }
