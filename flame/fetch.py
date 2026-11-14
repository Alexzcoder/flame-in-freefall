"""Download PSI combustion metadata, file manifests and run tables into data/raw/.

    python -m flame.fetch            # metadata + manifests + run tables (~22 MB), skips what exists
    python -m flame.fetch --reports  # + final reports / science-document PDFs (~126 MB, 42 files)
    python -m flame.fetch --force    # re-download everything

PSI has no documented API; these are the endpoints its web app uses (found in its JS bundle).
Media (video/zips, ~7.8 TB) is never downloaded here: runs reference it by file name.
"""
import json, os, sys, urllib.parse, urllib.request

API = "https://psi.nasa.gov/geode-py/ws"
RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")


class Fetcher:
    def __init__(self, raw=RAW, force=False):
        self.raw, self.force = raw, force

    def _get(self, url):
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read()

    def _save(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)  # atomic: an interrupted run never leaves a half file

    def _need(self, path):
        return self.force or not os.path.exists(path)

    def investigations(self):
        """All PSI investigations (search API). Returns the combustion ones' _source dicts."""
        path = os.path.join(self.raw, "investigations.json")
        if self._need(path):
            self._save(path, self._get(f"{API}/repo/search?q=&data_source=psi&data_type=investigation&size=500&from=0"))
        hits = json.load(open(path))["hits"]["hits"]
        return [h["_source"] for h in hits if h["_source"].get("Research Area") == "Combustion Science"]

    def manifest(self, acc):
        """Full investigation record incl. every file name/size."""
        path = os.path.join(self.raw, "manifests", f"{acc}.json")
        if self._need(path):
            self._save(path, self._get(f"{API}/repo/investigations/{acc}"))
        return json.load(open(path))

    def presigned_url(self, acc, file_name):
        q = urllib.parse.urlencode({"file": file_name, "redirect": "false"})
        url = self._get(f"{API}/studies/{acc}/download?{q}").decode().strip()
        if not url.startswith("https://"):
            raise RuntimeError(f"{acc}/{file_name}: {url[:200]}")
        return url

    def download(self, acc, file_name, subdir):
        path = os.path.join(self.raw, subdir, file_name)
        if self._need(path):
            self._save(path, self._get(self.presigned_url(acc, file_name)))
        return path

    def run_tables(self, acc):
        table = self.manifest(acc).get("experimentalTable")
        return [self.download(acc, t["file_name"], "run_tables") for t in table] if isinstance(table, list) else []

    def reports(self, acc):
        """PDFs in the investigation's 'Reports' and 'Science Documents' folders (final reports, test matrices)."""
        files = {}

        def walk(o):
            if isinstance(o, dict):
                if "file_name" in o and "file_size" in o:
                    files[o.get("remote_path", "")] = o["file_name"]
                    return
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(self.manifest(acc))
        out = []
        for path, name in sorted(files.items()):
            if name.lower().endswith(".pdf") and path.split("/")[4:5] in (["Reports"], ["Science Documents"]):
                try:
                    out.append(self.download(acc, name, "reports"))
                except Exception as e:  # PSI lists some files it can't serve (404); skip, don't abort the run
                    print(f"  skip {acc}/{name}: {e}", file=sys.stderr)
        return out

    def all(self, reports=False):
        invs = self.investigations()
        for s in invs:
            acc = s["Accession"]
            tables = self.run_tables(acc)
            pdfs = self.reports(acc) if reports else []
            print(f"{acc:8} {s.get('Acronym') or '':22} run tables: {len(tables)}" + (f"  report PDFs: {len(pdfs)}" if reports else ""))
        return invs


if __name__ == "__main__":
    Fetcher(force="--force" in sys.argv).all(reports="--reports" in sys.argv)
