"""Customers asking questions through AI clients, for twelve weeks.

Each question has a right answer (truth): a number from the version the publisher had live at that
moment, "no data" for a geography or year the catalogue does not cover, or "not in your plan" for a
premium statistic. A stand-in AI client answers by searching, picking the top result and fetching
it, the way an assistant with the MCP server does; without the platform it answers from memory.
People who notice a wrong statistic, or get nothing, rephrase once.

The platform only sees its own logs: searches, fetches, sessions, costs, and the wrong numbers
customers bother to report. `run` returns those (observed) and the outcome of every question (truth)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np

from .. import settings
from ..platform.grounding import Account, Grounding
from ..settings import u
from .catalogue import Statistic

TEMPLATES = [
    "What were {m} in {g} in {y}?",
    "{m} {g} {y}",
    "How high were {m} in {g} in {y}?",
    "{g} {m} for {y}",
    "Give me {m} in {g}, {y}",
    "What was the level of {m} in {g} in {y}",
    "{m} in {g} ({y})",
    "How big were {m} in {g} in {y}?",
]
FORECAST = ["What is the forecast for {m} in {g} in {y}?", "{m} {g} {y} forecast", "Projected {m} in {g} for {y}"]


@dataclass
class Question:
    qid: int
    ts: datetime
    account: Account
    client: str
    kind: str
    stat_id: str
    year: int
    text: str
    as_of: datetime | None
    gold: dict[str, Any]
    session: str
    attempt: int = 1


@dataclass
class Outcome:
    qid: int
    week: int
    plan: str
    client: str
    kind: str
    attempt: int
    result: str  # correct | wrong_number | stale | declined_right | missed
    answered_stat: str | None = None
    value: float | None = None
    cited: bool = False
    version: int | None = None
    ts: datetime | None = None
    account_id: str = ""
    latency_ms: float = 0.0
    calls: int = 0


@dataclass
class Run:
    outcomes: list[Outcome] = field(default_factory=list)
    tickets: list[dict[str, Any]] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)  # observed: queries and fetches per MCP session


def start() -> datetime:
    return datetime.combine(date.fromisoformat(str(settings.load("world")["start"])), datetime.min.time())


def accounts() -> list[Account]:
    out = []
    for plan, (n, _q) in settings.load("world")["consumers"]["plans"].items():
        out += [Account(f"{plan}-{k:04d}", plan) for k in range(n)]
    return out


def _pick(options: dict[str, float], *key: Any) -> str:
    x, acc = u(*key), 0.0
    for name, share in options.items():
        acc += share
        if x < acc:
            return name
    return list(options)[-1]


def gold_for(st: Statistic, year: int, when: datetime) -> dict[str, Any]:
    v = st.at(when)
    if v is None or year not in v["values"]:
        return {"answer": "no_data"}
    return {"answer": "value", "value": v["values"][year], "version": v["version"]}


def questions(stats: dict[str, Statistic]) -> list[Question]:
    w = settings.load("world")
    c = w["consumers"]
    cat = w["catalogue"]
    ids = sorted(stats)
    weights = np.array([1 / (1 + int(u("rank", s) * len(ids))) ** 0.8 for s in ids])
    weights /= weights.sum()
    weight_of = dict(zip(ids, weights, strict=True))
    cum: dict[tuple[str, ...], np.ndarray] = {}
    premium = [s for s in ids if stats[s].premium]
    standard = [s for s in ids if not stats[s].premium]
    revised = [s for s in ids if len(stats[s].versions) > 1]
    t0 = start()
    out: list[Question] = []
    rng = np.random.default_rng(w["seed"])
    for acc in accounts():
        rate = c["plans"][acc.plan][1]
        for week in range(w["weeks"]):
            for k in range(int(rng.poisson(rate))):
                key = (acc.account_id, week, k)
                ts = t0 + timedelta(days=7 * week + int(5 * u("day", *key)), hours=8 + 10 * u("hour", *key))
                kind = _pick(c["question_mix"], "kind", *key)
                pool = premium if kind == "premium" else standard
                if kind == "as_of":
                    pool = [s for s in revised if stats[s].versions[1]["published_at"] < ts and not stats[s].premium]
                    if not pool:  # nothing revised yet: an ordinary question
                        kind, pool = "plain", standard
                key_pool = tuple(pool)
                if key_pool not in cum:
                    p = np.array([weight_of[s] for s in pool])
                    cum[key_pool] = np.cumsum(p / p.sum())
                sid = pool[min(len(pool) - 1, int(np.searchsorted(cum[key_pool], rng.random())))]
                st = stats[sid]
                metric = cat["metrics"][st.metric]
                vocab, keywords = metric[4], metric[3]
                term = (
                    keywords[int(u("kw", *key) * len(keywords))]
                    if kind != "paraphrase"
                    else [x for x in vocab if x not in keywords][int(u("pv", *key) * (len(vocab) - 2)) % 3]
                )
                aliases = cat["geographies"][st.geo][1]
                geo_text = aliases[int(u("alias", *key) * len(aliases))]
                y_last = cat["years"][1]
                year = y_last - int(u("year", *key) ** 2 * 6)
                as_of = None
                if kind == "forecast":
                    year = int(cat["forecast_years"][0] + int(u("fy", *key) * 4))
                    text = FORECAST[int(u("t", *key) * len(FORECAST))]
                else:
                    text = TEMPLATES[int(u("t", *key) * len(TEMPLATES))]
                if kind == "uncovered":
                    if u("unc", *key) < 0.5:
                        geo_text = cat["uncovered_geographies"][int(u("ug", *key) * len(cat["uncovered_geographies"]))]
                    else:
                        year = cat["years"][0] - 1 - int(u("old", *key) * 8)
                text = text.format(m=term, g=geo_text, y=year)
                if kind == "as_of":
                    rev = st.versions[1]["published_at"]
                    as_of = rev - timedelta(days=1 + int(20 * u("asof", *key)))
                    text += f" as published on {as_of:%d %B %Y}"
                if kind == "uncovered":
                    gold = {"answer": "no_data"}
                elif kind == "premium" and acc.plan != "enterprise":
                    gold = {"answer": "not_entitled"}
                else:
                    gold = gold_for(st, year, as_of or ts)
                out.append(
                    Question(
                        len(out),
                        ts,
                        acc,
                        _pick(c["clients"], "client", acc.account_id),
                        kind,
                        sid,
                        year,
                        text,
                        as_of,
                        gold,
                        f"s{len(out)}",
                    )
                )
    out.sort(key=lambda q: (q.ts, q.qid))
    return out


def rephrase(q: Question, stats: dict[str, Statistic]) -> Question | None:
    """A user who noticed a miss tries once more: in the analysts' words half the time."""
    w = settings.load("world")
    if q.attempt > 1 or u("again", q.qid) >= w["consumers"]["reformulate_after_miss"] or q.kind == "uncovered":
        return None
    st = stats[q.stat_id]
    metric = w["catalogue"]["metrics"][st.metric]
    words = metric[3] if u("analyst", q.qid) < 0.5 else metric[4]
    term = words[int(u("rw", q.qid) * len(words))]
    geo = w["catalogue"]["geographies"][st.geo][0]
    text = f"{term} in {geo} in {q.year}" + (f" as published on {q.as_of:%d %B %Y}" if q.as_of else "")
    return Question(
        q.qid,
        q.ts + timedelta(minutes=1),
        q.account,
        q.client,
        q.kind,
        q.stat_id,
        q.year,
        text,
        q.as_of,
        q.gold,
        q.session,
        attempt=2,
    )


def from_memory(q: Question, stats: dict[str, Statistic]) -> tuple[str, float | None]:
    """An assistant without the platform: answers anyway most of the time, from an old revision, roughly."""
    m = settings.load("world")["ungrounded_model"]
    if u("anyway", q.qid, q.attempt) >= m["answers_anyway"]:
        return "declined", None
    st = stats[q.stat_id]
    v = st.versions[0]["values"].get(q.year)
    if v is None:
        v = list(st.versions[0]["values"].values())[-1]
    z = math.sqrt(-2 * math.log(max(1e-12, u("z1", q.qid)))) * math.cos(2 * math.pi * u("z2", q.qid))
    return "answered", v * (1 + m["relative_error_sd"] * z)


def judge(q: Question, said: str, value: float | None, version: int | None, stat: str | None) -> str:
    g = q.gold
    if g["answer"] in ("no_data", "not_entitled"):
        return "declined_right" if said in ("declined", "not_entitled") else "wrong_number"
    if said != "answered":
        return "missed"
    if stat is not None and stat != q.stat_id:
        return "wrong_number"
    if value is not None and abs(value - g["value"]) <= 1e-9 * max(1.0, abs(g["value"])):
        return "correct"
    if stat == q.stat_id and version is not None and version != g["version"]:
        return "stale"
    return "wrong_number"


def ask(q: Question, g: Grounding | None, stats: dict[str, Statistic], run: Run) -> Outcome:
    wc = settings.load("world")["grounded_client"]
    week = (q.ts - start()).days // 7
    o = Outcome(
        q.qid, week, q.account.plan, q.client, q.kind, q.attempt, "missed", ts=q.ts, account_id=q.account.account_id
    )
    if g is None:
        said, value = from_memory(q, stats)
        o.result = judge(q, said, value, None, None)
        o.value = value
        return o
    found = g.search(q.account, q.text, q.ts)
    o.calls, o.latency_ms = 1, g.meter.events[-1]["latency_ms"] if found["status"] != "budget_exhausted" else 0.0
    session = {
        "session": q.session,
        "account_id": q.account.account_id,
        "client": q.client,
        "ts": q.ts,
        "query": q.text,
        "results": [h["stat_id"] for h in found["results"]],
        "fetched": None,
        "status": found["status"],
    }
    run.sessions.append(session)
    if not found["results"]:
        guess = u("mem-nomatch", q.qid, q.attempt) < wc["no_match_answers_from_memory"]
        if q.gold["answer"] == "value":
            said, value = from_memory(q, stats) if guess else ("declined", None)
            o.result = judge(q, said, value, None, "memory")
        else:
            o.result = "wrong_number" if guess else "declined_right"  # a made-up number for data that does not exist
        if o.result != "declined_right":
            _again(q, o, g, stats, run)
        return o
    top = found["results"][0]
    res = g.get(q.account, top["stat_id"], q.year, q.ts, q.as_of)
    o.calls += 1
    o.latency_ms += res.get("latency_ms", 0.0)
    session["fetched"] = top["stat_id"]
    session["fetch_status"] = res["status"]
    if res["status"] == "ok":
        o.result = judge(q, "answered", res["value"], res["version"], top["stat_id"])
        o.answered_stat, o.value, o.cited, o.version = top["stat_id"], res["value"], True, res["version"]
    elif res["status"] == "not_entitled":
        if u("mem-ent", q.qid) < wc["not_entitled_answers_from_memory"]:
            said, value = from_memory(q, stats)
            o.result = "wrong_number" if said == "answered" else judge(q, "not_entitled", None, None, None)
        else:
            o.result = judge(q, "not_entitled", None, None, None)
    elif res["status"] == "error":
        if u("mem-err", q.qid) < wc["generic_error_answers_from_memory"]:
            said, value = from_memory(q, stats)
            o.result = "wrong_number" if said == "answered" else judge(q, "declined", None, None, None)
        else:
            o.result = judge(q, "declined", None, None, None)
    else:
        o.result = judge(q, "declined", None, None, None)
    wrong_stat = top["stat_id"] != q.stat_id
    if (
        o.result in ("wrong_number", "stale")
        and o.cited
        and u("report", q.qid, q.attempt) < settings.load("world")["consumers"]["report_wrong_number"]
    ):
        run.tickets.append(
            {
                "ts": q.ts,
                "account_id": q.account.account_id,
                "stat_id": top["stat_id"],
                "kind": "wrong_number",
                "query": q.text,
            }
        )
    if (wrong_stat and u("notice", q.qid, q.attempt) < wc["notices_wrong_statistic"]) or o.result == "missed":
        _again(q, o, g, stats, run)
    return o


def _again(q: Question, o: Outcome, g: Grounding, stats: dict[str, Statistic], run: Run) -> None:
    nxt = rephrase(q, stats)
    if nxt is not None:
        run.outcomes.append(ask(nxt, g, stats, run))


def run(qs: list[Question], g: Grounding | None, stats: dict[str, Statistic]) -> Run:
    r = Run()
    for q in qs:
        r.outcomes.append(ask(q, g, stats, r))
    return r
