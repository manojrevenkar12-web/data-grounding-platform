"""The platform decides from what it records. It never reads the simulated world: how people
really phrase questions, what is really right, which deliveries were really broken."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parents[1] / "src" / "dgp"
SHIPPING = ["platform", "service", "product/telemetry.py", "product/scoring.py"]
FORBIDDEN = ("dgp.sim", "dgp.evals", "dgp.pipeline")


def files() -> list[Path]:
    out: list[Path] = []
    for name in SHIPPING:
        p = SRC / name
        out += sorted(p.rglob("*.py")) if p.is_dir() else [p]
    return out


def resolve(node: ast.ImportFrom, path: Path) -> str:
    if not node.level:
        return node.module or ""
    pkg = path.relative_to(SRC.parent).with_suffix("").parts[: -node.level]
    return ".".join([*pkg, *([node.module] if node.module else [])])


@pytest.mark.parametrize("path", files(), ids=lambda p: str(p.relative_to(SRC)))
def test_shipping_code_never_reads_the_world(path):
    for node in ast.walk(ast.parse(path.read_text())):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = resolve(node, path)
            names = [base, *(f"{base}.{a.name}" for a in node.names)]
        assert not any(n.startswith(FORBIDDEN) for n in names), f"{path.name} imports {names}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "truth":
                raise AssertionError(f"{path.name} calls settings.truth()")
            if (
                node.func.attr == "load"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "world"
            ):
                raise AssertionError(f"{path.name} reads config/world.yaml")


def test_the_scan_covers_the_platform():
    assert len(files()) >= 10


def test_relative_imports_resolve():
    assert resolve(ast.parse("from ..sim import world").body[0], SRC / "platform" / "x.py") == "dgp.sim"
