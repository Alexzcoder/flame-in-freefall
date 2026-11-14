"""Full-text search over everything we know in words: investigation objectives, publication abstracts,
and NASA report pages. Every hit carries a citation (investigation, document, page / DOI).

    python -m flame.search                 # rebuild dataset/documents.jsonl (needs data/raw/text, see flame.docs)
    python -m flame.search "extinction velocity PMMA"

    from flame.search import Index
    Index().search("smoke detector false alarm", k=5)

ponytail: SQLite FTS5 BM25 (stdlib, in-memory, ~2k docs). Add embeddings only if keyword search proves too weak.
"""
import glob, hashlib, json, os, re, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "dataset", "documents.jsonl")


def build_documents():
    from .schema import Dataset
    ds = Dataset.from_json(os.path.join(ROOT, "dataset", "flame_runs.json"))
    docs = []
    for i in ds.investigations:
        if i.objective:
            docs.append({"id": f"{i.id}/objective", "kind": "objective", "investigations": [i.id],
                         "title": f"{i.acronym}: {i.title}", "cite": f"PSI {i.id} investigation record", "text": i.objective})
    for p in json.load(open(os.path.join(ROOT, "dataset", "publications.json"))):
        docs.append({"id": p["id"], "kind": "abstract" if p["abstract"] else "title", "investigations": p["investigations"],
                     "title": p["title"], "cite": f"{p['venue'] or ''} {p['year'] or ''} doi:{p['doi']}".strip() if p["doi"] else p["title"],
                     "text": p["abstract"] or p["title"]})
    seen = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "raw", "text", "*.json"))):
        d = json.load(open(f))
        name = re.sub(r"^PSI-\d+_(Reports|Science Documents)_", "", d["file"])[:-4]
        for n, text in enumerate(d["pages"], 1):
            if len(text) < 200:  # covers, blank and figure-only pages
                continue
            h = hashlib.sha1(text.encode()).hexdigest()
            if h in seen:  # same manual filed under two investigations (SAME, ACME ISRD)
                if d["investigation"] not in seen[h]["investigations"]:
                    seen[h]["investigations"].append(d["investigation"])
                continue
            doc = {"id": f"{d['file']}#p{n}", "kind": "report", "investigations": [d["investigation"]],
                   "title": name, "cite": f"{d['file']}, p. {n}", "text": text}
            seen[h] = doc
            docs.append(doc)
    with open(DOCS, "w") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return docs


# Domain synonyms: user words -> the terms NASA documents actually use. Expanded at query time (ORed in).
SYNONYMS = {
    "cotton": ["sibal"], "fabric": ["sibal", "nomex", "textile"], "cloth": ["sibal", "nomex", "fabric"],
    "acrylic": ["pmma"], "plexiglass": ["pmma"], "plastic": ["pmma", "polymer"], "polymethylmethacrylate": ["pmma"],
    "spread": ["propagation"], "propagation": ["spread"], "extinguish": ["extinction", "quench"],
    "suppress": ["suppression", "extinguish", "inert"], "suppressant": ["suppression", "diluent", "inert"],
    "smoke": ["aerosol", "particulate", "soot"], "detector": ["detection", "sensor"], "alarm": ["detector", "detection"],
    "moon": ["lunar"], "lunar": ["moon"], "mars": ["martian"], "habitat": ["spacecraft", "cabin"],
    "oxygen": ["o2"], "o2": ["oxygen"], "fire": ["flame", "combustion"], "droplet": ["drop"],
    "airflow": ["flow", "velocity"], "ventilation": ["flow", "velocity"], "gravity": ["microgravity"],
}


def expand(words):
    out = list(words)
    for w in words:
        out += [x for x in SYNONYMS.get(w, []) if x not in out]
    return out


class Index:
    def __init__(self, path=DOCS):
        self.docs = [json.loads(l) for l in open(path)]
        self.db = sqlite3.connect(":memory:")
        self.db.execute("create virtual table d using fts5(title, text, tokenize='porter unicode61')")
        self.db.executemany("insert into d(rowid, title, text) values (?, ?, ?)",
                            [(n, d["title"], d["text"]) for n, d in enumerate(self.docs)])

    def search(self, query, k=10, investigation=None, kind=None):
        """BM25-ranked hits. query: plain words (ORed); investigation: 'PSI-25'; kind: objective|abstract|title|report."""
        words = expand(re.findall(r"\w+", query.lower()))
        if not words:
            return []
        rows = self.db.execute("select rowid, bm25(d, 2.0, 1.0) as s from d where d match ? order by s limit ?",
                               (" OR ".join(f'"{w}"' for w in words), k * 20)).fetchall()
        hits = []
        for rowid, score in rows:
            doc = self.docs[rowid]
            if (investigation and investigation not in doc["investigations"]) or (kind and doc["kind"] != kind):
                continue
            hits.append({**doc, "score": round(-score, 3)})
            if len(hits) == k:
                break
        return hits


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for h in Index().search(" ".join(sys.argv[1:]), k=8):
            print(f"{h['score']:6.2f}  [{h['kind']:9}] {','.join(h['investigations']):16} {h['cite'][:70]}\n        {h['text'][:160]!r}")
    else:
        docs = build_documents()
        from collections import Counter
        print(f"wrote {DOCS}: {len(docs)} documents {dict(Counter(d['kind'] for d in docs))}, "
              f"{os.path.getsize(DOCS) / 1e6:.1f} MB")
        ix = Index()
        top = ix.search("extinction velocity opposed flow PMMA", k=3)
        assert any("PSI-25" in h["investigations"] for h in top), top
        assert ix.search("smoke aging detector", k=3)[0]["investigations"][0] in ("PSI-101", "PSI-102", "PSI-115", "PSI-47")
        assert all(h["investigations"] == ["PSI-69"] or "PSI-69" in h["investigations"]
                   for h in ix.search("droplet", k=5, investigation="PSI-69"))
        assert any("sibal" in h["text"].lower() for h in ix.search("cotton fabric flame spread", k=5)), "synonym expansion"
        print("search self-check ok")
