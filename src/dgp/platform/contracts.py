"""Data contracts (Open Data Contract Standard v3.1) at the platform's door.

Two checks, both run by producers in their own CI and again by the platform on every delivery:

- `validate(rows)`: a delivery against its contract: required properties, types, patterns and
  ranges, no missing values, each metric keeps its registered unit, and versions only go up.
- `compatibility(old, new)`: a contract change against the one consumers rely on. Removing or
  retyping a property, making an optional one required, or changing a unit is breaking and needs a
  new major version; adding an optional property is not."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .. import settings

TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "date": str}


@dataclass
class Verdict:
    accepted: bool
    problems: list[str] = field(default_factory=list)
    rows: int = 0

    def add(self, msg: str) -> None:
        if msg not in self.problems and len(self.problems) < 20:
            self.problems.append(msg)
        self.accepted = False


def load(topic: str, root: Path | None = None) -> dict[str, Any]:
    return yaml.safe_load(((root or settings.CONTRACTS) / f"{topic}.yaml").read_text())


def all_contracts(root: Path | None = None) -> dict[str, dict[str, Any]]:
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted((root or settings.CONTRACTS).glob("*.yaml"))}


def properties(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["name"]: p for p in contract["schema"][0]["properties"]}


def units(contract: dict[str, Any]) -> dict[str, str]:
    return next(c["value"] for c in contract.get("customProperties", []) if c["property"] == "units")


def structural(contract: dict[str, Any]) -> list[str]:
    """What a contract itself must have to be accepted (the strict ODCS 3.1 subset this platform uses)."""
    out = []
    for key in ("apiVersion", "kind", "id", "version", "status", "schema", "team"):
        if key not in contract:
            out.append(f"missing {key}")
    if contract.get("kind") != "DataContract":
        out.append("kind must be DataContract")
    if not str(contract.get("apiVersion", "")).startswith("v3."):
        out.append("apiVersion must be v3.x")
    try:
        units(contract)
    except StopIteration:
        out.append("customProperties.units is required: the registered unit of every metric")
    return out


def validate(contract: dict[str, Any], rows: list[dict[str, Any]], published: dict[str, int] | None = None) -> Verdict:
    """`published`: the highest version already live per stat_id."""
    v = Verdict(True, rows=len(rows))
    props = properties(contract)
    registry = units(contract)
    published = published or {}
    for r in rows:
        extra = set(r) - set(props)
        if extra:
            v.add(f"unknown properties: {', '.join(sorted(extra))}")
        for name, p in props.items():
            if name not in r or r[name] is None:
                if p.get("required"):
                    v.add(f"{name} is required and missing")
                continue
            t = TYPES[p["logicalType"]]
            if (isinstance(r[name], bool) and p["logicalType"] in ("integer", "number")) or not isinstance(r[name], t):
                v.add(f"{name} must be a {p['logicalType']}")
            opts = p.get("logicalTypeOptions", {})
            if (
                "minimum" in opts
                and isinstance(r[name], (int, float))
                and not opts["minimum"] <= r[name] <= opts["maximum"]
            ):
                v.add(f"{name} out of range [{opts['minimum']}, {opts['maximum']}]")
            if "pattern" in opts and isinstance(r[name], str):
                import re

                if not re.match(opts["pattern"], r[name]):
                    v.add(f"{name} does not match {opts['pattern']}")
        metric = r.get("metric")
        if metric in registry and r.get("unit") != registry[metric]:
            v.add(f"{metric} is registered in {registry[metric]!r}, delivered in {r.get('unit')!r}")
        elif metric not in registry:
            v.add(f"metric {metric!r} is not registered in this contract")
        sid = r.get("stat_id")
        if sid in published and isinstance(r.get("version"), int) and r["version"] <= published[sid]:
            v.add(f"{sid}: version {r['version']} is not newer than the live version {published[sid]}")
    return v


def compatibility(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Breaking changes between two contract versions, and whether the version bump admits them."""
    a, b = properties(old), properties(new)
    breaking, additive = [], []
    for name, p in a.items():
        if name not in b:
            breaking.append(f"removed {name}")
            continue
        q = b[name]
        if q["logicalType"] != p["logicalType"]:
            breaking.append(f"{name}: {p['logicalType']} -> {q['logicalType']}")
        if q.get("required") and not p.get("required"):
            breaking.append(f"{name} became required")
    for name, q in b.items():
        if name not in a:
            (breaking if q.get("required") else additive).append(
                f"added {'required' if q.get('required') else 'optional'} {name}"
            )
    ua, ub = units(old), units(new)
    for m, unit in ua.items():
        if m in ub and ub[m] != unit:
            breaking.append(f"{m}: unit {unit} -> {ub[m]}")
        if m not in ub:
            breaking.append(f"metric {m} removed")
    major_old, major_new = (int(str(c["version"]).split(".")[0]) for c in (old, new))
    ok = not breaking or major_new > major_old
    return {
        "breaking": breaking,
        "additive": additive,
        "allowed": ok,
        "reason": "breaking changes need a new major version" if not ok else "compatible",
    }
