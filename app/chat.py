"""Chat agent: DeepSeek (OpenAI-compatible tool calling) over the dataset and the report/paper search index.

The model never sees the dataset directly. It must call tools, and every number/claim it states should come
from a tool result, with the citation. Keys come from the environment or <repo>/.env (see ranking/llm.py).
"""
import json
import os
import urllib.error
import urllib.request

from ranking.llm import provider

MAX_STEPS = 6
SYSTEM = """You are the research assistant of "Flame in Freefall", a NASA Space Apps dashboard about spacecraft fire safety.
Your knowledge comes ONLY from tools over NASA's PSI microgravity combustion data: 1,624 experiment runs from
9 investigations (FLEX, CFI, CFI-G, Flame Design, SPICE, BASS-II, SAFFIRE I-III), metadata for 24 investigations,
299 papers and 1,559 pages of NASA final reports.

Rules:
- Always use tools before answering factual questions. Never invent numbers, runs, or findings.
- Cite every factual sentence with the source in square brackets: run ids like [PSI-69/20CAL08], or the `cite`
  string from search_documents like [PSI-25_Reports_BASS-II Summary Report.pdf, p. 34].
- Say clearly when the data does not cover something (e.g. no solid-fuel runs above 22% O2; no partial-gravity data;
  only 633 runs have measured outcomes). Flag assumed values (run.assumed) and censored burn times.
- Units: O2 as % or fraction (state which), pressure in kPa and psi (1 psi = 6.895 kPa), flow in cm/s.
- Be concise: short paragraphs or bullets, for engineers and researchers. Answer in the user's language."""

TOOLS = [
    {"type": "function", "function": {
        "name": "search_documents",
        "description": "Keyword search over NASA final reports (page level), paper abstracts and investigation objectives. "
                       "Use for findings, methods, explanations. Pass key terms, not a full question.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "investigation": {"type": "string", "description": "optional PSI id, e.g. PSI-25"},
            "kind": {"type": "string", "enum": ["report", "abstract", "objective", "title"]}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "find_runs",
        "description": "Filter experiment runs. Returns count and up to `limit` runs with conditions and outcomes. "
                       "O2 as mole fraction (0.21 = air), pressure kPa. Inverse flames (burner-stream O2) are excluded.",
        "parameters": {"type": "object", "properties": {
            "investigation": {"type": "string"}, "fuel": {"type": "string"},
            "phase": {"type": "string", "enum": ["solid", "liquid", "gas"]},
            "o2_min": {"type": "number"}, "o2_max": {"type": "number"},
            "pressure_min_kpa": {"type": "number"}, "pressure_max_kpa": {"type": "number"},
            "has_outcome": {"type": "boolean"},
            "result": {"type": "string", "enum": ["burnout", "extinction", "disruption", "no_ignition", "terminated"]},
            "limit": {"type": "integer", "default": 15}}}}},
    {"type": "function", "function": {
        "name": "nearest_runs",
        "description": "Closest real experiments to given conditions, with a coverage verdict (well_covered/sparse/no_data).",
        "parameters": {"type": "object", "properties": {
            "o2_frac": {"type": "number"}, "pressure_kpa": {"type": "number"},
            "flow_cm_s": {"type": "number", "default": 10}, "fuel_phase": {"type": "string", "enum": ["solid", "liquid", "gas"]}},
            "required": ["o2_frac", "pressure_kpa"]}}},
    {"type": "function", "function": {
        "name": "rank_investigations",
        "description": "Rank investigations by relevance to a habitat scenario (iss, moon_base, pressurized_rover, mars_base), "
                       "optionally for one fire-safety pillar.",
        "parameters": {"type": "object", "properties": {
            "scenario": {"type": "string", "enum": ["iss", "moon_base", "pressurized_rover", "mars_base"]},
            "focus": {"type": "string", "enum": ["prevention", "detection", "suppression"]}},
            "required": ["scenario"]}}},
    {"type": "function", "function": {
        "name": "get_investigation",
        "description": "Profile of one investigation: objective, hardware, fuels, tested O2/pressure/flow ranges, outcomes, papers.",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {
        "name": "compare_investigations",
        "description": "Computed similarities and differences between 2-3 investigations.",
        "parameters": {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}}},
                       "required": ["ids"]}}},
]


def _run_row(r):
    a, o = r.conditions.atmosphere, r.outcome
    return {"id": r.id, "fuel": r.conditions.fuel.name, "phase": r.conditions.fuel.phase,
            "o2_frac": a.o2_frac, "pressure_kpa": a.pressure_kpa, "flow_cm_s": r.conditions.flow.velocity_cm_s,
            "outcome": {k: v for k, v in vars(o).items() if v is not None}, "assumed": r.assumed or None}


def call_tool(name, args, sources):
    from .main import data
    ds, profs, pubs, ix = data()
    if name == "search_documents":
        hits = ix.search(args["query"], k=5, investigation=args.get("investigation"), kind=args.get("kind"))
        for h in hits:
            sources.setdefault(h["cite"], {"cite": h["cite"], "title": h["title"], "kind": h["kind"],
                                           "investigations": h["investigations"]})
        return [{"cite": h["cite"], "investigations": h["investigations"], "text": h["text"][:1500]} for h in hits]
    if name == "find_runs":
        def ok(r):
            a, f = r.conditions.atmosphere, r.conditions.fuel
            return (r.conditions.o2_location == "ambient"
                    and (not args.get("investigation") or r.investigation == args["investigation"])
                    and (not args.get("fuel") or args["fuel"].lower() in f.name)
                    and (not args.get("phase") or f.phase == args["phase"])
                    and (args.get("o2_min") is None or (a.o2_frac is not None and a.o2_frac >= args["o2_min"]))
                    and (args.get("o2_max") is None or (a.o2_frac is not None and a.o2_frac <= args["o2_max"]))
                    and (args.get("pressure_min_kpa") is None or (a.pressure_kpa or 0) >= args["pressure_min_kpa"])
                    and (args.get("pressure_max_kpa") is None or (a.pressure_kpa is not None and a.pressure_kpa <= args["pressure_max_kpa"]))
                    and (args.get("has_outcome") is None or r.has_outcome == args["has_outcome"])
                    and (not args.get("result") or r.outcome.result == args["result"]))
        rows = [r for r in ds.runs if ok(r)]
        return {"count": len(rows), "runs": [_run_row(r) for r in rows[:min(int(args.get("limit") or 15), 30)]]}
    if name == "nearest_runs":
        return nearest_runs_compact(ds, args)
    if name == "rank_investigations":
        from ranking.rank import rank
        out = rank(ds, args["scenario"], args.get("focus"), profs)
        return {"scenario": out["scenario"], "results": [{k: r[k] for k in ("rank", "id", "acronym", "score", "n_close_runs",
                                                                            "reasons", "caveats")} for r in out["results"][:8]]}
    if name == "get_investigation":
        p = profs.get(args["id"])
        if not p:
            return {"error": f"unknown id {args['id']}"}
        return {**P_public(p), "publications": [{"title": x["title"], "year": x["year"], "doi": x["doi"],
                                                 "abstract": (x["abstract"] or "")[:400]} for x in pubs.get(args["id"], [])[:8]]}
    if name == "compare_investigations":
        from ranking.compare import compare
        c = compare(ds, args["ids"][:3], profiles=profs)
        return {k: c[k] for k in ("similarities", "differences")}
    return {"error": f"unknown tool {name}"}


def nearest_runs_compact(ds, args):
    from ranking.nearest import nearest_runs
    out = nearest_runs(ds, args["o2_frac"], args["pressure_kpa"], args.get("flow_cm_s") or 10.0, 0.0, args.get("fuel_phase"), 6)
    for m in out["matches"]:
        m.pop("media", None)
    return out


def P_public(p):
    from ranking.profiles import public
    return public(p)


def _post(url, key, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def answer(messages):
    prov, key, _ = provider()
    if prov != "deepseek":
        return {"answer": "The AI assistant isn't configured: set DEEPSEEK_API_KEY (in .env locally, or the Vercel project env).",
                "trace": [], "sources": [], "model": None}
    model = os.environ.get("CHAT_MODEL", "deepseek-chat")
    convo = [{"role": "system", "content": SYSTEM}] + messages
    trace, sources = [], {}
    for _ in range(MAX_STEPS):
        try:
            resp = _post("https://api.deepseek.com/chat/completions", key,
                         {"model": model, "messages": convo, "tools": TOOLS, "temperature": 0.2, "max_tokens": 1200})
        except urllib.error.HTTPError as e:
            return {"answer": f"AI provider error {e.code}: {e.read().decode(errors='replace')[:300]}",
                    "trace": trace, "sources": list(sources.values()), "model": model}
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"answer": msg.get("content") or "", "trace": trace, "sources": list(sources.values()), "model": model}
        convo.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
                result = call_tool(c["function"]["name"], args, sources)
            except Exception as e:  # bad args from the model: report back so it can retry
                args, result = {}, {"error": str(e)[:200]}
            trace.append({"tool": c["function"]["name"], "args": args})
            convo.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result, default=str)[:12000]})
    return {"answer": "I couldn't finish within the tool-call limit; try a narrower question.",
            "trace": trace, "sources": list(sources.values()), "model": model}
