"""GET /api/dl?acc=PSI-25&file=<name> -> 302 to a fresh PSI presigned S3 URL. Vercel function + used by view.py locally."""
import re, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler


def presigned(acc, name):
    q = urllib.parse.urlencode({"file": name, "redirect": "false"})
    url = urllib.request.urlopen(f"https://psi.nasa.gov/geode-py/ws/studies/{acc}/download?{q}", timeout=30).read().decode().strip()
    if not url.startswith("https://psi-repo-prod.s3.amazonaws.com/"):
        raise ValueError(url[:200])
    return url


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        acc, name = q.get("acc", [""])[0], q.get("file", [""])[0]
        if not re.fullmatch(r"PSI-\d+", acc) or not name:
            return self.send_error(400, "need acc=PSI-n and file=")
        try:
            loc = presigned(acc, name)
        except Exception as e:
            return self.send_error(502, str(e)[:200])
        self.send_response(302)
        self.send_header("Location", loc)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
