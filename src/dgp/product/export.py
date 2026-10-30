"""`dgp export-web`: the dashboard's data, written to web/public/data from the reports."""

from __future__ import annotations

import json
from pathlib import Path

from .. import settings


def run(out: Path | None = None) -> list[str]:
    out = out or settings.ROOT / "web" / "public" / "data"
    out.mkdir(parents=True, exist_ok=True)
    r = json.loads((settings.REPORTS / "results.json").read_text())
    ev = r["evaluation"]["variants"]
    heldout = []
    base = settings.REPORTS / "heldout"
    if base.exists():
        for p in sorted(base.glob("*/first_run.json")):
            h = json.loads(p.read_text())
            heldout.append(
                {k: h[k] for k in ("set", "status", "cases")}
                | {
                    "configs": {c: {k: v for k, v in x.items() if k != "rows"} for c, x in h["configs"].items()},
                    "misses": [row for row in h["configs"].get("plan", {}).get("rows", []) if not row["right"]],
                }
            )
    files = {
        "summary.json": {
            "observed": r["observed"],
            "gate": r["gate"],
            "represents": r["represents"],
            "truth_north_star": r["truth"]["north_star_per_week"],
        },
        "bets.json": {
            "scored": r["scored"],
            "roadmap": r["roadmap"],
            "plan": r["plan"],
            "variants": {
                k: {
                    "summary": {kk: vv for kk, vv in v["summary"].items() if kk != "by_kind"},
                    "delta": v["delta"],
                    "measured_against": v.get("measured_against", "today"),
                }
                for k, v in ev.items()
            },
        },
        "glossary.json": r["glossary"],
        "heldout.json": heldout,
    }
    for name, data in files.items():
        (out / name).write_text(json.dumps(data, separators=(",", ":"), default=str))
    return sorted(files)
