"""Optional AI text, from DeepSeek or Anthropic (Claude). Standard library only.

Everything works without it: with no key, or if a call fails, complete() returns None and callers
fall back to template text.

Setup (pick one provider):
    cp ranking/.env.example .env          # in the repo root; .env is git-ignored
    # then put your key in .env, e.g.  DEEPSEEK_API_KEY=sk-...

    python3 -m ranking.llm                # self-test: shows provider/model and makes one tiny call

Environment variables (also read from .env in the repo root):
    DEEPSEEK_API_KEY      key for DeepSeek
    ANTHROPIC_API_KEY     key for Anthropic
    RANKING_LLM_PROVIDER  "deepseek" | "anthropic" | "auto" (default: auto = DeepSeek if its key is set)
    RANKING_LLM_MODEL     override the model (defaults below)
"""
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_MODELS = {"deepseek": "deepseek-flash", "anthropic": "claude-sonnet-5-5"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACEHOLDER_PREFIXES = ("your-", "<", "sk-xxx", "replace")


def _load_dotenv():
    """Read KEY=value lines from <repo>/.env without overriding variables already set."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def _key(name):
    v = os.environ.get(name, "").strip()
    return None if not v or v.lower().startswith(PLACEHOLDER_PREFIXES) else v


def provider():
    """(provider name, api key, model) or (None, None, None) if no usable key."""
    _load_dotenv()
    choice = os.environ.get("RANKING_LLM_PROVIDER", "auto").lower()
    order = [choice] if choice in DEFAULT_MODELS else ["deepseek", "anthropic"]
    for p in order:
        k = _key("DEEPSEEK_API_KEY" if p == "deepseek" else "ANTHROPIC_API_KEY")
        if k:
            return p, k, os.environ.get("RANKING_LLM_MODEL") or DEFAULT_MODELS[p]
    return None, None, None


def _post(url, headers, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={**headers, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _deepseek(key, model, prompt, max_tokens):
    url, headers = "https://api.deepseek.com/chat/completions", {"Authorization": f"Bearer {key}"}
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "stream": False, "thinking": {"type": "disabled"}}
    try:
        data = _post(url, headers, body)
    except urllib.error.HTTPError as e:
        if e.code != 400:
            raise
        # if the thinking switch isn't accepted, retry without it and leave room for reasoning tokens
        body.pop("thinking")
        body["max_tokens"] = max_tokens * 4
        data = _post(url, headers, body)
    return (data["choices"][0]["message"].get("content") or "").strip()


def _anthropic(key, model, prompt, max_tokens):
    data = _post("https://api.anthropic.com/v1/messages",
                 {"x-api-key": key, "anthropic-version": "2023-06-01"},
                 {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]})
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


_DISABLED = False  # set after an auth/quota error so a batch run doesn't repeat it hundreds of times


def complete(prompt, max_tokens=400, verbose=False):
    global _DISABLED
    if _DISABLED:
        return None
    p, key, model = provider()
    if not p:
        if verbose:
            print("llm: no API key set (DEEPSEEK_API_KEY or ANTHROPIC_API_KEY); using template text", file=sys.stderr)
        return None
    try:
        text = (_deepseek if p == "deepseek" else _anthropic)(key, model, prompt, max_tokens)
        return text or None
    except Exception as e:  # network, auth, quota... never crash the pipeline over optional text
        detail = e.read().decode(errors="replace")[:300] if isinstance(e, urllib.error.HTTPError) else ""
        print(f"llm: {p} call failed ({e}) {detail} -> using template text", file=sys.stderr)
        if isinstance(e, urllib.error.HTTPError) and e.code in (401, 402, 403):
            _DISABLED = True
            print("llm: key rejected or out of credit; skipping AI for the rest of this run", file=sys.stderr)
        return None


if __name__ == "__main__":
    p, key, model = provider()
    if not p:
        print("No usable key found. Copy ranking/.env.example to .env in the repo root and add your key.")
        sys.exit(1)
    print(f"provider: {p}   model: {model}   key: ...{key[-4:]}")
    out = complete("Reply with exactly: ok", max_tokens=20, verbose=True)
    print("response:", out if out else "(none, see error above)")
    sys.exit(0 if out else 1)
