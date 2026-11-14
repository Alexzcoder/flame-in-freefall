"""Publication abstracts for every investigation -> dataset/publications.json.

    python -m flame.papers

Sources, in order (raw responses cached in data/raw/papers/, so reruns are offline):
  1. OpenAlex (by DOI, batched)      - abstract when the publisher shares it, open-access PDF link
  2. Semantic Scholar (by DOI, batch) - fills many abstracts OpenAlex lacks
  3. NASA NTRS (by title)            - NASA reports/conference papers, often with abstract + free PDF
  4. OpenAlex title search           - for publications listed without a DOI
Elsevier abstracts are mostly unavailable to scripts; those records keep title/venue/year/DOI only.
"""
import difflib, hashlib, html, json, os, re, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "raw", "papers")
OUT = os.path.join(ROOT, "dataset", "publications.json")
UA = {"User-Agent": "flame-in-freefall (NASA Space Apps research script)"}


def norm(t):
    return re.sub(r"[^a-z0-9]+", " ", html.unescape(t or "").lower()).strip()


def similar(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def cached(key, fetch):
    path = os.path.join(CACHE, hashlib.sha1(key.encode()).hexdigest()[:16] + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    data = fetch()
    os.makedirs(CACHE, exist_ok=True)
    json.dump({"key": key, "data": data}, open(path, "w"))
    return {"key": key, "data": data}


def get(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={**UA, **({"Content-Type": "application/json"} if body else {})})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            if e.code == 404:
                return None
            raise


def inverted_to_text(inv):
    if not inv:
        return None
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _, w in pos)


def openalex_by_doi(dois):
    out = {}
    for k in range(0, len(dois), 50):
        chunk = dois[k:k + 50]
        q = urllib.parse.urlencode({"filter": "doi:" + "|".join(chunk), "per-page": 50,
                                    "select": "doi,title,publication_year,abstract_inverted_index,best_oa_location,primary_location"})
        for w in cached("openalex:" + "|".join(chunk), lambda: get("https://api.openalex.org/works?" + q))["data"]["results"]:
            out[w["doi"].replace("https://doi.org/", "").lower()] = w
    return out


def s2_by_doi(dois):
    out = {}
    for k in range(0, len(dois), 400):
        chunk = dois[k:k + 400]
        res = cached("s2:" + "|".join(chunk), lambda: get(
            "https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,abstract,year,venue",
            {"ids": ["DOI:" + d for d in chunk]}))["data"]
        for d, w in zip(chunk, res):
            if w:
                out[d] = w
    return out


def ntrs_by_title(title):
    q = urllib.parse.urlencode({"q": html.unescape(title), "page.size": 5})
    res = cached("ntrs:" + norm(title), lambda: get("https://ntrs.nasa.gov/api/citations/search?" + q))["data"] or {}
    best = max(res.get("results", []), key=lambda r: similar(r.get("title", ""), title), default=None)
    return best if best and similar(best["title"], title) >= 0.9 else None


def openalex_by_title(title):
    q = urllib.parse.urlencode({"search": html.unescape(title)[:250], "per-page": 3,
                                "select": "doi,title,publication_year,abstract_inverted_index,best_oa_location,primary_location"})
    res = cached("openalex-title:" + norm(title), lambda: get("https://api.openalex.org/works?" + q))["data"] or {}
    best = max(res.get("results", []), key=lambda w: similar(w.get("title") or "", title), default=None)
    return best if best and similar(best.get("title") or "", title) >= 0.9 else None


def build(investigations):
    """investigations: list of schema.Investigation. Returns list of publication dicts (deduplicated)."""
    pubs = {}
    for inv in investigations:
        for p in inv.publications:
            doi = (p.get("doi") or "").strip().lower() or None
            key = doi or "title:" + norm(p["title"])
            rec = pubs.setdefault(key, {"id": key, "title": html.unescape(p["title"]).strip(), "doi": doi, "year": None,
                                        "venue": None, "abstract": None, "abstract_source": None, "oa_pdf": None,
                                        "ntrs_id": None, "investigations": []})
            if inv.id not in rec["investigations"]:
                rec["investigations"].append(inv.id)
    dois = sorted(r["doi"] for r in pubs.values() if r["doi"])
    oa, s2 = openalex_by_doi(dois), s2_by_doi(dois)
    for rec in pubs.values():
        w = oa.get(rec["doi"]) if rec["doi"] else openalex_by_title(rec["title"])
        if w:
            rec["year"] = w.get("publication_year")
            rec["venue"] = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
            rec["oa_pdf"] = (w.get("best_oa_location") or {}).get("pdf_url")
            if not rec["doi"] and w.get("doi"):
                rec["doi"] = w["doi"].replace("https://doi.org/", "").lower()
            if a := inverted_to_text(w.get("abstract_inverted_index")):
                rec["abstract"], rec["abstract_source"] = a, "openalex"
        if not rec["abstract"] and (s := s2.get(rec["doi"])) and s.get("abstract"):
            rec["abstract"], rec["abstract_source"] = s["abstract"], "semantic_scholar"
            rec["year"] = rec["year"] or s.get("year")
            rec["venue"] = rec["venue"] or s.get("venue")
        n = ntrs_by_title(rec["title"])
        if n:
            rec["ntrs_id"] = n["id"]
            pdf = next((d["links"]["pdf"] for d in n.get("downloads") or [] if d.get("links", {}).get("pdf")), None)
            rec["oa_pdf"] = rec["oa_pdf"] or (f"https://ntrs.nasa.gov{pdf}" if pdf else None)
            if not rec["abstract"] and n.get("abstract"):
                rec["abstract"], rec["abstract_source"] = n["abstract"], "ntrs"
        if rec["abstract"]:
            rec["abstract"] = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", rec["abstract"]))).strip()
    return sorted(pubs.values(), key=lambda r: (r["investigations"][0], -(r["year"] or 0), r["title"]))


if __name__ == "__main__":
    import collections
    from .schema import Dataset
    ds = Dataset.from_json(os.path.join(ROOT, "dataset", "flame_runs.json"))
    pubs = build(ds.investigations)
    json.dump(pubs, open(OUT, "w"), indent=1, ensure_ascii=False)
    n = len(pubs)
    src = collections.Counter(p["abstract_source"] for p in pubs)
    print(f"wrote {OUT}: {n} publications, {n - src[None]} with abstract ({(n - src[None]) / n:.0%}): {dict(src)}")
    print(f"  with free PDF link: {sum(1 for p in pubs if p['oa_pdf'])}, in NTRS: {sum(1 for p in pubs if p['ntrs_id'])}")
    per = collections.defaultdict(lambda: [0, 0])
    for p in pubs:
        for i in p["investigations"]:
            per[i][0] += 1
            per[i][1] += bool(p["abstract"])
    for i, (a, b) in sorted(per.items(), key=lambda x: int(x[0].split("-")[1])):
        print(f"  {i:8} {b:3}/{a:3} with abstract")
