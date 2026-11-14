"""Chat agent: DeepSeek (OpenAI-compatible tool calling) over the dataset and the report/paper search index.

The model never sees the dataset directly. It must call tools, and every number/claim it states should come
from a tool result, with the citation. Keys come from the environment or <repo>/.env (see ranking/llm.py).
"""
import json
import os
import re
import urllib.error
import urllib.request

from ranking.llm import provider

MAX_STEPS = 6
SYSTEM = """You are the expert research assistant of "Flame in Freefall", a NASA Space Apps dashboard on spacecraft fire safety.
Audience: researchers, aerospace engineers, students. Think like a combustion scientist advising a habitat designer.

## Background you may use without citation (general physics, not data)
- In microgravity there is no buoyant convection: flames are diffusion-controlled, often spherical, cooler and slower.
- Two extinction limits in forced flow: blowoff at high flow (too little residence time, kinetic limit) and
  quenching at very low flow (radiative heat loss dominates). Ventilation flow therefore matters a lot in space.
- Droplets follow the d^2-law: d^2 = d0^2 - K*t; K is the burning-rate constant (mm^2/s).
- Fire safety has three pillars: prevention (material flammability, ignition), detection (smoke/aerosol),
  suppression (inerting, CO2, N2, He, water mist, depressurisation).
- Planned lunar habitats: ~30%+ O2 at ~10.2 psi (70.3 kPa); ISS: ~21% O2 at 14.7 psi (101.3 kPa).

## Data rules (everything about the experiments must come from tools)
- Always use tools before stating any experimental fact. Never invent numbers, runs, findings or citations.
- Cite every data sentence in square brackets with a FULL source each time (no "same", "ibid", "op. cit."):
  run ids like [PSI-69/20CAL08], or the exact `cite` string from search_documents like
  [PSI-25_Reports_BASS-II Summary Report.pdf, p. 34], or an investigation id like [PSI-25].
- Tool results contain `caveats`. Repeat the relevant ones: assumed (not measured) values, censored burn times,
  inverse flames, no outcome recorded. Never present an assumed value as measured.
- When the data doesn't cover the question, say so plainly and say what the nearest evidence is.
- Prefer search_documents for findings/explanations (NASA final reports are the best source), and find_runs /
  nearest_runs for numbers. Use at most 4 tool calls in total, then answer.
- Units: say whether O2 is % or mole fraction; pressure in kPa and psi; flow in cm/s.
- Be concise: lead with the answer, then bullets. Answer in the user's language.

## What the dataset contains (computed from it, use to plan tool calls)
{brief}"""

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


FUEL_SYNONYMS = {"cotton": ["sibal"], "fabric": ["sibal", "nomex"], "cloth": ["sibal", "nomex"], "acrylic": ["pmma"],
                 "plexiglass": ["pmma"], "plastic": ["pmma", "silicone"], "wax": ["candle wax"], "dodecane": ["n-dodecane"]}


def run_caveats(r):
    out = [f"{p.split('.')[-1]} is ASSUMED (cabin air), not measured" for p in r.assumed]
    if r.outcome.censored:
        out.append("burn time is a LOWER BOUND (censored: run stopped or droplet disrupted, not natural extinction)")
    if r.conditions.o2_location == "burner_stream":
        out.append("inverse flame: o2_frac is the burner stream, not the surrounding atmosphere")
    if not r.has_outcome:
        out.append("no outcome recorded for this run")
    return out


def _run_row(r):
    a, o = r.conditions.atmosphere, r.outcome
    row = {"id": r.id, "fuel": r.conditions.fuel.name, "phase": r.conditions.fuel.phase,
           "o2_frac": a.o2_frac, "pressure_kpa": a.pressure_kpa, "flow_cm_s": r.conditions.flow.velocity_cm_s,
           "outcome": {k: v for k, v in vars(o).items() if v is not None}}
    if c := run_caveats(r):
        row["caveats"] = c
    return row


def _fuel_match(query, name):
    q = query.lower().strip()
    return q in name or any(alt in name for alt in FUEL_SYNONYMS.get(q, []))


def brief():
    """Expert brief computed from the dataset (cached with data())."""
    from .main import data
    ds, profs, _, _ = data()
    solid_o2 = max(r.conditions.atmosphere.o2_frac for r in ds.runs
                   if r.conditions.fuel.phase == "solid" and r.conditions.atmosphere.o2_frac is not None)
    lines = [f"- {len(ds.runs)} runs; {sum(r.has_outcome for r in ds.runs)} have measured outcomes (usable as evidence of "
             f"what happened); {sum(bool(r.outcome.censored) for r in ds.runs)} burn times are censored.",
             f"- KNOWN GAPS: no solid-fuel run above {solid_o2 * 100:.1f}% O2; all data is microgravity (no lunar/Mars "
             "gravity); smoke experiments (SAME, SAME-R) are not in the run table (use search_documents); flame spread "
             "rate is measured for very few runs (mostly in report figures).",
             "- Fuel names in data: pmma (acrylic), sibal (cotton/fiberglass fabric), nomex, silicone, candle wax, "
             "methanol, heptane, n-dodecane, ethylene, ethane, propane, propylene, butane, methane.",
             "- Investigations (id = acronym | family | runs (with outcome) | fuels | O2 range measured | outcomes | note):"]
    for p in profs.values():
        o2 = p["o2_frac_range"]
        lines.append(f"  {p['id']} = {p['acronym']} | {p['category']} | {p['n_runs']} ({p['n_with_outcome']}) | "
                     f"{', '.join(p['fuels'][:6]) or '-'} | {f'{o2[0]*100:.0f}-{o2[1]*100:.0f}%' if o2 else '-'} | "
                     f"{', '.join(p['outcome_fields']) or 'none'}{' | ' + p['note'] if p['note'] else ''}")
    return "\n".join(lines)


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
                    and (not args.get("fuel") or _fuel_match(args["fuel"], f.name))
                    and (not args.get("phase") or f.phase == args["phase"])
                    and (args.get("o2_min") is None or (a.o2_frac is not None and a.o2_frac >= args["o2_min"]))
                    and (args.get("o2_max") is None or (a.o2_frac is not None and a.o2_frac <= args["o2_max"]))
                    and (args.get("pressure_min_kpa") is None or (a.pressure_kpa or 0) >= args["pressure_min_kpa"])
                    and (args.get("pressure_max_kpa") is None or (a.pressure_kpa is not None and a.pressure_kpa <= args["pressure_max_kpa"]))
                    and (args.get("has_outcome") is None or r.has_outcome == args["has_outcome"])
                    and (not args.get("result") or r.outcome.result == args["result"]))
        rows = [r for r in ds.runs if ok(r)]
        n_asm, n_cens = sum(bool(r.assumed) for r in rows), sum(bool(r.outcome.censored) for r in rows)
        notes = ([f"{n_asm} of {len(rows)} matching runs have ASSUMED (not measured) pressure/O2"] if n_asm else []) + \
                ([f"{n_cens} matching runs have censored burn times (lower bounds)"] if n_cens else [])
        by_inv = {}
        for r in rows:
            by_inv[r.investigation] = by_inv.get(r.investigation, 0) + 1
        return {"count": len(rows), "with_outcome": sum(r.has_outcome for r in rows), "by_investigation": by_inv,
                "caveats": notes,
                "runs": [_run_row(r) for r in rows[:min(int(args.get("limit") or 15), 30)]]}
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
    by_id = {r.id: r for r in ds.runs}
    for m in out["matches"]:
        m.pop("media", None)
        m["caveats"] = run_caveats(by_id[m["run_id"]])
    return out


def P_public(p):
    from ranking.profiles import public
    return public(p)


_BRIEF = None


def _brief():
    global _BRIEF
    if _BRIEF is None:
        _BRIEF = brief()
    return _BRIEF


CITE = re.compile(r"\[([^\]]{3,200})\]")


def unverified_citations(text, seen):
    """Bracketed citations whose run id / document / investigation never appeared in any tool result this turn."""
    bad = []
    for m in CITE.finditer(text):
        for part in re.split(r"\s*[;,]\s*(?=PSI-|doi|[A-Z][^,;]*\.pdf)", m.group(1)):
            part = part.strip()
            key = re.sub(r",?\s*pp?\.\s*[\d\u2013-]+$", "", part)  # "file.pdf, p. 34" -> must see "file.pdf, p. 34" itself
            ok = part in seen or (key != part and part in seen) or (re.fullmatch(r"PSI-\d+", part) and f'"{part}"' in seen) \
                or (key.startswith("doi:") and key[4:] in seen) or (re.fullmatch(r"PSI-\d+/\S+", part) and part in seen)
            if not ok and (part.startswith("PSI-") or ".pdf" in part or part.startswith("doi:")):
                bad.append(part)
    return sorted(set(bad))


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
    model = os.environ.get("CHAT_MODEL", "deepseek-flash")
    convo = [{"role": "system", "content": SYSTEM.format(brief=_brief())}] + messages
    trace, sources, seen = [], {}, [_brief()]  # the computed brief is a legitimate source for investigation ids
    for step in range(MAX_STEPS):
        last = step == MAX_STEPS - 1
        if last:  # out of tool rounds: answer with what has been gathered instead of giving up
            convo.append({"role": "user", "content": "Answer now using only the tool results above. Say what is missing."})
        body = {"model": model, "messages": convo, "temperature": 0.2, "max_tokens": 1200, "thinking": {"type": "disabled"},
                **({} if last else {"tools": TOOLS})}
        try:
            try:
                resp = _post("https://api.deepseek.com/chat/completions", key, body)
            except urllib.error.HTTPError as e:
                if e.code != 400:
                    raise
                body.pop("thinking")  # model doesn't accept the switch: retry without it
                resp = _post("https://api.deepseek.com/chat/completions", key, body)
        except urllib.error.HTTPError as e:
            return {"answer": f"AI provider error {e.code}: {e.read().decode(errors='replace')[:300]}",
                    "trace": trace, "sources": list(sources.values()), "model": model}
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            text = msg.get("content") or ""
            return {"answer": text, "trace": trace, "sources": list(sources.values()), "model": model,
                    "unverified": unverified_citations(text, "\n".join(seen))}
        convo.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
                result = call_tool(c["function"]["name"], args, sources)
            except Exception as e:  # bad args from the model: report back so it can retry
                args, result = {}, {"error": str(e)[:200]}
            trace.append({"tool": c["function"]["name"], "args": args,
                          **({"error": result["error"]} if isinstance(result, dict) and "error" in result else {})})
            content = json.dumps(result, default=str, ensure_ascii=False)[:12000]
            seen.append(content)
            convo.append({"role": "tool", "tool_call_id": c["id"], "content": content})
    return {"answer": "I couldn't finish within the tool-call limit; try a narrower question.",
            "trace": trace, "sources": list(sources.values()), "model": model}
