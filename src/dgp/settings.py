"""Where things live, and the settings. Business and platform settings are in config/, never in code.

config/world.yaml describes the simulated world: how people really phrase questions, what an
assistant says without tools, how often wrong numbers get reported. Only dgp.sim and dgp.evals may
read it, or anything under build/truth (tests/test_isolation.py checks)."""

from __future__ import annotations

import hashlib
import os
from functools import cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
CONTRACTS = ROOT / "contracts"
BUILD = Path(os.environ.get("DGP_BUILD", ROOT / "build"))
REPORTS = Path(os.environ.get("DGP_REPORTS", ROOT / "reports"))
HELDOUT = ROOT / "heldout"
DBT = ROOT / "dbt"


@cache
def load(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG / f"{name}.yaml").read_text())


def warehouse() -> Path:
    """The DuckDB warehouse (Snowflake in production): raw landing tables and the dbt marts."""
    return BUILD / "warehouse.duckdb"


def landing() -> Path:
    """Where producers drop dataset files (S3 in production)."""
    return BUILD / "landing"


def telemetry() -> Path:
    return BUILD / "telemetry"


def truth() -> Path:
    return BUILD / "truth"


def u(*key: Any, seed: int = 2026) -> float:
    """A uniform draw fixed by its key, so every variant of the platform faces the same world."""
    h = hashlib.sha256("|".join(map(str, (seed, *key))).encode()).digest()
    return int.from_bytes(h[:8], "little") / 2**64
