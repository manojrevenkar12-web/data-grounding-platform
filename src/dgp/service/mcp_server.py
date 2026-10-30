"""The grounding service as an MCP server, for Claude, Copilot, Langdock, n8n and any MCP client.

Tools: `search_statistics`, `get_statistic` (a year, optionally as of a date, with the citation to
show) and `cite`. A resource template exposes each statistic as `stat://{stat_id}`. The prompt
`answer_with_statistics` tells a model how to use them: quote the number with its citation, say
"not covered" or "not in your plan" when the tool says so, and never estimate a number itself.

Over stdio the account comes from DGP_API_KEY; over HTTP from the X-API-Key header of the session."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..platform.grounding import Account, Grounding

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


def build(g: Grounding, account: Account) -> MCPServer:
    mcp = MCPServer(
        name="data-grounding",
        instructions=(
            "Verified business statistics with citations. Search, then fetch the statistic for the year asked. "
            "Quote the value with its citation. If a tool says not covered, no such year or not in your plan, say so: "
            "never estimate a number yourself."
        ),
    )

    def now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    @mcp.tool(annotations=READ)
    def search_statistics(query: str, limit: int = 5) -> dict[str, Any]:
        """Find statistics for a question ("EV sales in Germany 2023"). Results say whether your plan includes them."""
        return g.search(account, query, now(), limit)

    @mcp.tool(annotations=READ)
    def get_statistic(stat_id: str, year: int | None = None, as_of: str | None = None) -> dict[str, Any]:
        """A statistic's value for a year (default: the latest actual year), from the version live at `as_of`
        (ISO date, default: now), with its citation and any newer revision."""
        when = datetime.fromisoformat(as_of) if as_of else None
        return g.get(account, stat_id, year, now(), when)

    @mcp.tool(annotations=READ)
    def cite(stat_id: str, version: int | None = None) -> dict[str, Any]:
        """The citation to show for a statistic (a version, or the live one)."""
        s = g.c.stats.get(stat_id)
        if s is None:
            return {"status": "not_found"}
        v = next((x for x in s.versions if x["version"] == version), None) if version else s.version_at(now())
        if v is None:
            return {"status": "not_found"}
        return g.cite(account, stat_id, v["version"], v["published_at"], now())

    @mcp.resource("stat://{stat_id}")
    def statistic(stat_id: str) -> dict[str, Any]:
        """The live version of a statistic, every year, with its citation."""
        s = g.c.stats.get(stat_id)
        if s is None or not g.entitled(account, stat_id):
            return {"status": "not_available"}
        v = s.version_at(now())
        return {
            "title": s.title,
            "unit": s.unit,
            "version": v["version"],
            "values": {str(y): val for y, (val, _f) in sorted(s.values[v["version"]].items())},
            "citation": g.cite(account, stat_id, v["version"], v["published_at"], now()),
        }

    @mcp.prompt()
    def answer_with_statistics(question: str) -> str:
        """How to answer a question with verified statistics."""
        return (
            f"Answer: {question}\n1. search_statistics with the question.\n2. get_statistic for the best match "
            "and the year asked.\n3. Quote the value and unit with the citation's title, publisher and URL.\n"
            "4. If the tool says not covered, no such year or not in your plan, say exactly that."
        )

    return mcp


def from_env() -> MCPServer:  # pragma: no cover - wiring for `dgp serve-mcp`
    from .. import settings
    from ..platform.catalog import Catalog
    from .keys import Keys

    acc = Keys(settings.BUILD / "keys.json").account(os.environ.get("DGP_API_KEY"))
    if acc is None:
        raise SystemExit("set DGP_API_KEY to a key issued with `dgp keys issue`")
    return build(Grounding(Catalog.load()), acc)
