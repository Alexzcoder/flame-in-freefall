"""Flame in Freefall dashboard API (FastAPI). Serves public/ as the frontend.

    uvicorn app.main:app --reload        # http://localhost:8000

Everything is read-only over dataset/ (flame) and ranking/ (Kai). Loaded once per process.
"""
import json
import os
import time
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from flame.schema import Dataset
from flame.search import Index
from ranking import profiles as P
from ranking.compare import compare
from ranking.nearest import nearest_runs
from ranking.rank import rank
from ranking.scenarios import SCENARIOS, custom

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = FastAPI(title="Flame in Freefall API")


@lru_cache(maxsize=1)
def data():
    ds = Dataset.from_json(os.path.join(ROOT, "dataset", "flame_runs.json"))
    pubs = json.load(open(os.path.join(ROOT, "dataset", "publications.json")))
    by_inv = {}
    for p in pubs:
        for i in p["investigations"]:
            by_inv.setdefault(i, []).append(p)
    return ds, P.build(ds), by_inv, Index()


def scenario_from(scenario, o2, pressure, flow, gravity):
    if scenario != "custom":
        if scenario not in SCENARIOS:
            raise HTTPException(400, f"unknown scenario {scenario!r}; use {list(SCENARIOS)} or custom")
        return SCENARIOS[scenario]
    if o2 is None or pressure is None:
        raise HTTPException(400, "custom scenario needs o2 and pressure")
    return custom(o2, pressure, gravity_g=gravity, flow_cm_s=flow)


@app.get("/api/meta")
def meta():
    ds, profs, _, ix = data()
    return {"n_runs": len(ds.runs), "n_with_outcome": sum(r.has_outcome for r in ds.runs),
            "n_investigations": len(ds.investigations), "n_documents": len(ix.docs),
            "scenarios": {k: v.to_dict() for k, v in SCENARIOS.items()},
            "investigations": [{"id": p["id"], "acronym": p["acronym"], "title": p["title"], "category": p["category"],
                                "n_runs": p["n_runs"], "n_with_outcome": p["n_with_outcome"]} for p in profs.values()]}


@app.get("/api/coverage")
def coverage():
    """One point per run with ambient O2: what has been tested (for the O2-vs-pressure map)."""
    ds, profs, _, _ = data()
    pts = []
    for r in ds.runs:
        a = r.conditions.atmosphere
        if r.conditions.o2_location != "ambient" or a.o2_frac is None or a.pressure_kpa is None:
            continue
        pts.append({"id": r.id, "inv": profs[r.investigation]["acronym"], "category": profs[r.investigation]["category"],
                    "o2_pct": round(a.o2_frac * 100, 2), "pressure_kpa": a.pressure_kpa, "has_outcome": r.has_outcome,
                    "assumed": bool(r.assumed), "fuel": r.conditions.fuel.name})
    return pts


@app.get("/api/rank")
def api_rank(scenario: str = "moon_base", focus: str | None = None, o2: float | None = None,
             pressure: float | None = None, flow: float = 10.0, gravity: float = 0.0):
    ds, profs, _, _ = data()
    if focus not in (None, "", "prevention", "detection", "suppression"):
        raise HTTPException(400, "focus must be prevention | detection | suppression")
    return rank(ds, scenario_from(scenario, o2, pressure, flow, gravity), focus or None, profs)


@app.get("/api/nearest")
def api_nearest(o2: float = Query(..., gt=0, le=1), pressure: float = Query(..., gt=0), flow: float = 10.0,
                gravity: float = 0.0, phase: str | None = None, k: int = Query(8, le=50)):
    ds, *_ = data()
    if phase not in (None, "", "solid", "liquid", "gas"):
        raise HTTPException(400, "phase must be solid | liquid | gas")
    return nearest_runs(ds, o2, pressure, flow, gravity, phase or None, k)


@app.get("/api/investigations/{inv_id}")
def investigation(inv_id: str):
    _, profs, pubs, _ = data()
    if inv_id not in profs:
        raise HTTPException(404, "unknown investigation")
    return {**P.public(profs[inv_id]), "publications": pubs.get(inv_id, [])}


@app.get("/api/compare")
def api_compare(ids: str):
    ds, profs, _, _ = data()
    lst = [i.strip() for i in ids.split(",") if i.strip()]
    if not 2 <= len(lst) <= 3:
        raise HTTPException(400, "give 2-3 ids, e.g. ids=PSI-25,PSI-99")
    try:
        return compare(ds, lst, profiles=profs)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/search")
def api_search(q: str, investigation: str | None = None, kind: str | None = None, k: int = Query(8, le=30)):
    *_, ix = data()
    return [{k_: h[k_] for k_ in ("id", "kind", "investigations", "title", "cite", "score")} | {"text": h["text"][:600]}
            for h in ix.search(q, k=k, investigation=investigation or None, kind=kind or None)]


class ChatIn(BaseModel):
    messages: list[dict]


CHAT_LIMIT, CHAT_WINDOW_S = 20, 600   # per client IP
_chat_hits: dict[str, list[float]] = {}


@app.post("/api/chat")
def api_chat(body: ChatIn, request: Request):
    # ponytail: in-memory limiter, per function instance (not global); enough to stop a casual credit drain.
    # Upgrade path: Vercel Firewall rate-limit rule or a Redis counter if the link gets shared widely.
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    now = time.time()
    hits = [t for t in _chat_hits.get(ip, []) if now - t < CHAT_WINDOW_S]
    if len(hits) >= CHAT_LIMIT:
        raise HTTPException(429, f"Too many questions: limit is {CHAT_LIMIT} per {CHAT_WINDOW_S // 60} minutes.")
    _chat_hits[ip] = hits + [now]
    from .chat import answer
    msgs = [m for m in body.messages if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)][-12:]
    if not msgs or msgs[-1]["role"] != "user":
        raise HTTPException(400, "last message must be from the user")
    if len(msgs[-1]["content"]) > 2000:
        raise HTTPException(400, "question too long (max 2,000 characters)")
    return answer([{"role": m["role"], "content": m["content"][:4000]} for m in msgs])


if os.path.isdir(os.path.join(ROOT, "public")):
    from fastapi.responses import FileResponse

    @app.get("/v2", include_in_schema=False)
    def v2_page():  # local dev; on Vercel /v2 is a rewrite in vercel.json
        return FileResponse(os.path.join(ROOT, "public", "v2.html"))

    # on Vercel public/ is served by the CDN, not the function, so this mount is local-only too
    app.mount("/", StaticFiles(directory=os.path.join(ROOT, "public"), html=True), name="static")
