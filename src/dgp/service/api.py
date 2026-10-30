"""The grounding API (what API customers and the MCP server call), over the
same Grounding service as the simulation. Every request needs an API key; the key decides the
account, its plan, its entitlements and its budget."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from ..platform.catalog import Catalog
from ..platform.grounding import Account, Grounding
from .keys import Keys


def create_app(warehouse: Path | None = None, keys: Path | None = None, catalog: Catalog | None = None) -> FastAPI:
    from .. import settings

    g = Grounding(catalog or Catalog.load(warehouse))
    k = Keys(keys or settings.BUILD / "keys.json")
    app = FastAPI(title="Data grounding API", version="1.0.0")
    app.state.grounding, app.state.keys = g, k

    def caller(x_api_key: Annotated[str | None, Header()] = None) -> Account:
        acc = k.account(x_api_key)
        if acc is None:
            raise HTTPException(401, "a valid X-API-Key is required")
        return acc

    Who = Annotated[Account, Depends(caller)]

    def now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"ok": True, "statistics": len(g.c.stats), "features": g.c.features}

    @app.get("/v1/search")
    def search(
        who: Who, q: Annotated[str, Query(min_length=2, max_length=300)], limit: Annotated[int, Query(ge=1, le=20)] = 5
    ) -> dict[str, Any]:
        out = g.search(who, q, now(), limit)
        if out["status"] == "budget_exhausted":
            raise HTTPException(402, "the monthly budget of this plan is used up")
        return out

    @app.get("/v1/statistics/{stat_id}")
    def statistic(who: Who, stat_id: str, year: int | None = None, as_of: datetime | None = None) -> dict[str, Any]:
        out = g.get(who, stat_id, year, now(), as_of.replace(tzinfo=None) if as_of else None)
        if out["status"] == "budget_exhausted":
            raise HTTPException(402, "the monthly budget of this plan is used up")
        if out["status"] == "not_found":
            raise HTTPException(404, f"no statistic {stat_id}")
        if out["status"] in ("not_entitled", "error"):
            raise HTTPException(403, out.get("message", "not included in your plan"))
        return out

    @app.get("/v1/usage")
    def usage(who: Who) -> dict[str, Any]:
        mine = [e for e in g.meter.events if e["account_id"] == who.account_id]
        return {
            "account_id": who.account_id,
            "plan": who.plan,
            "calls": len(mine),
            "cost_eur": round(sum(e["cost_eur"] for e in mine), 4),
        }

    return app
