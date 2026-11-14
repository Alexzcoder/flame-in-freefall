"""PSI report PDFs -> page-level text, cached in data/raw/text/<pdf name>.json as {"file", "investigation", "pages": [str]}.

    python -m flame.docs     # after: python -m flame.fetch --reports

Page granularity is deliberate: every fact pulled from a report can cite (file, page).
"""
import glob, json, os, re, sys

from pypdf import PdfReader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDFS = os.path.join(ROOT, "data", "raw", "reports")
TEXT = os.path.join(ROOT, "data", "raw", "text")


def extract(pdf):
    out = os.path.join(TEXT, os.path.basename(pdf) + ".json")
    if os.path.exists(out):
        return json.load(open(out))
    pages = []
    for p in PdfReader(pdf).pages:
        try:
            t = p.extract_text() or ""
        except Exception:  # a single broken page shouldn't lose the document
            t = ""
        pages.append(re.sub(r"[ \t]+", " ", t).strip())
    doc = {"file": os.path.basename(pdf), "investigation": re.match(r"(PSI-\d+)_", os.path.basename(pdf))[1], "pages": pages}
    os.makedirs(TEXT, exist_ok=True)
    json.dump(doc, open(out, "w"))
    return doc


def all_docs():
    return [extract(p) for p in sorted(glob.glob(os.path.join(PDFS, "*.pdf")))]


if __name__ == "__main__":
    for d in all_docs():
        chars = sum(map(len, d["pages"]))
        flag = "  <- scanned/image-only?" if chars < 200 * len(d["pages"]) else ""
        print(f"{d['investigation']:8} {len(d['pages']):4} pages {chars:8,} chars  {d['file'][:70]}{flag}", file=sys.stdout)
