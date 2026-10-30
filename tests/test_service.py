"""The grounding API and the MCP server, over the small catalogue."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from mcp.client.client import Client

from dgp.platform.catalog import Catalog
from dgp.platform.grounding import Account, Grounding
from dgp.service.api import create_app
from dgp.service.keys import Keys
from dgp.service.mcp_server import build
from tests.conftest import small


def test_keys_are_hashed_and_checked(tmp_path):
    k = Keys(tmp_path / "keys.json")
    key = k.issue("acme", "team")
    assert key not in (tmp_path / "keys.json").read_text()
    assert k.account(key) == Account("acme", "team")
    assert k.account(key[:-1] + ("x" if key[-1] != "x" else "y")) is None and k.account(None) is None


def test_api(tmp_path):
    keys = Keys(tmp_path / "keys.json")
    team, ent = keys.issue("acme", "team"), keys.issue("bigco", "enterprise")
    c = TestClient(create_app(keys=tmp_path / "keys.json", catalog=Catalog(small())))
    assert c.get("/v1/search", params={"q": "EV sales"}).status_code == 401
    hits = c.get("/v1/search", params={"q": "EV sales Germany"}, headers={"X-API-Key": team}).json()
    assert hits["results"][0]["stat_id"] == "ev_sales-DE"
    ok = c.get("/v1/statistics/gdp-US", params={"year": 2024}, headers={"X-API-Key": team})
    assert ok.status_code == 200 and ok.json()["citation"]["version"] == 1
    assert c.get("/v1/statistics/beer_sales-DE", headers={"X-API-Key": team}).status_code == 403
    assert c.get("/v1/statistics/beer_sales-DE", headers={"X-API-Key": ent}).status_code == 200
    assert c.get("/v1/statistics/nope", headers={"X-API-Key": ent}).status_code == 404
    old = c.get(
        "/v1/statistics/ev_sales-DE", params={"year": 2024, "as_of": "2026-01-20T00:00:00"}, headers={"X-API-Key": ent}
    ).json()
    assert old["version"] == 1 and old["revision_notice"]["version"] == 2
    usage = c.get("/v1/usage", headers={"X-API-Key": team}).json()
    assert usage["calls"] == 3 and usage["cost_eur"] > 0
    assert c.get("/healthz").json()["statistics"] == 4


def payload(r):
    if r.structured_content:
        return r.structured_content.get("result", r.structured_content)
    return json.loads(r.content[0].text)


async def test_mcp_server_tools_resources_and_prompt():
    g = Grounding(Catalog(small()))
    async with Client(build(g, Account("acme", "team"))) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert names == {"search_statistics", "get_statistic", "cite"}
        assert all(t.annotations.read_only_hint for t in (await c.list_tools()).tools)
        hits = payload(await c.call_tool("search_statistics", {"query": "EV sales France"}))
        assert hits["results"][0]["stat_id"] == "ev_sales-FR"
        out = payload(
            await c.call_tool("get_statistic", {"stat_id": "ev_sales-DE", "year": 2024, "as_of": "2026-01-20"})
        )
        assert out["version"] == 1 and out["citation"]["licence"].startswith("Licensed to acme")
        assert payload(await c.call_tool("get_statistic", {"stat_id": "beer_sales-DE"}))["status"] == "not_entitled"
        assert payload(await c.call_tool("cite", {"stat_id": "gdp-US"}))["version"] == 1
        assert payload(await c.call_tool("cite", {"stat_id": "nope"}))["status"] == "not_found"
        res = await c.read_resource("stat://gdp-US")
        assert '"2024"' in res.contents[0].text
        denied = await c.read_resource("stat://beer_sales-DE")
        assert "not_available" in denied.contents[0].text
        prompt = await c.get_prompt("answer_with_statistics", {"question": "EV sales in Germany?"})
        assert "search_statistics" in prompt.messages[0].content.text
