"""Numbers for the pitch deck (public/pitch.html), taken from the project's own outputs, never typed in.

    python -m flame.pitch_export     # → public/pitch/data.json (+ a few images)

Sources: dataset/flame_runs.json, dataset/documents.jsonl, dataset/predict_eval.json, public/station/simparams.json,
dataset/loo_eval.md, dataset/spread_eval.md, public/models/flame_emulator.json, public/station/insights.json,
public/station/risk.json, data/calib/log.jsonl (tuning history), the search index (a real citation).
"""
import json, math, os, re, shutil, subprocess  # noqa

from flame.media import ROOT

OUT = os.path.join(ROOT, "public", "pitch")


def J(rel):
    return json.load(open(os.path.join(ROOT, rel)))


def nn_assets(em):
    """Neural-network slide: a mosaic of real training simulations, and network predictions for held-out fires
    computed with the exported weights (public/models/flame_emulator.json, the file the website runs)."""
    import base64
    import numpy as np
    import torch
    from PIL import Image
    d = np.load(os.path.join(ROOT, "data", "emulator", "sims.npz"))
    X, IMG, S = d["X"].astype(np.float32), d["img"].astype(np.float32), d["S"]
    conds = json.loads(str(d["conds"]))
    n = len(X)
    test = torch.randperm(n, generator=torch.Generator().manual_seed(0))[:n // 10].numpy()  # emulator.py's held-out set
    lit = np.nonzero(S[:, 0] > 0.5)[0]
    bright = lit[np.argsort(-IMG[lit].max(axis=(1, 2, 3)))]
    rng = np.random.default_rng(1)
    pick = rng.choice(bright[:4000], 60, replace=False)
    up = lambda im, k: Image.fromarray((np.clip(im * 1.6, 0, 1) * 255).astype(np.uint8)).resize((24 * k, 32 * k), Image.BICUBIC)
    mos = Image.new("RGB", (12 * 96, 5 * 128))
    for i, j in enumerate(pick):
        mos.paste(up(IMG[j], 4), ((i % 12) * 96, (i // 12) * 128))
    mos.save(os.path.join(OUT, "nn_mosaic.jpg"), quality=88)
    # forward pass of the exported ensemble in numpy (float16 weights, like the browser)
    f16 = lambda b: np.frombuffer(base64.b64decode(b), "<f2").astype(np.float32)
    mean, basis = f16(em["img_mean"]), f16(em["img_basis"]).reshape(em["pcs"], -1)
    mu, sd = np.array(em["mu"], np.float32), np.array(em["sd"], np.float32)
    def predict(x):
        h0, out = (x - mu) / sd, 0
        for L in em["members"]:
            h = h0
            for k in range(3):
                l = L[k]; h = f16(l["w"]).reshape(l["out"], l["in"]) @ h + f16(l["b"]); h = h / (1 + np.exp(-h))
            coef = f16(L[3]["w"]).reshape(L[3]["out"], -1) @ h + f16(L[3]["b"])
            out = out + np.clip(mean + coef @ basis, 0, 1) / len(em["members"])
        return out.reshape(32, 24, 3)
    want = []
    for fuel in ("fabric", "pmma", "droplet", "burner"):
        cand = [j for j in test if conds[j]["fuel"] == fuel and S[j, 0] > 0.5 and IMG[j].max() > 0.35]
        want.append(sorted(cand, key=lambda j: -IMG[j].max())[len(cand) // 4])
    cand = [j for j in test if conds[j]["gravity_g"] > 0.9 and S[j, 0] > 0.5 and IMG[j].max() > 0.35]
    want.append(sorted(cand, key=lambda j: -IMG[j].max())[len(cand) // 4])
    pairs = Image.new("RGB", (5 * 150, 2 * 200 + 10), (7, 9, 15))
    labels = []
    for i, j in enumerate(want):
        pairs.paste(up(IMG[j], 5), (i * 150 + 15, 0))
        pairs.paste(up(predict(X[j]), 5), (i * 150 + 15, 210))
        c = conds[j]
        labels.append(f"{c['fuel']} · {c['gravity_g']:.2g} g · {c['o2'] * 100:.0f}% O₂")
    pairs.save(os.path.join(OUT, "nn_pairs.jpg"), quality=92)
    return {"sims": int(n), "test": int(len(test)), "inputs": em["inputs"], "hidden": em["members"][0][0]["out"],
            "layers": 3, "pcs": em["pcs"], "members": len(em["members"]), "pair_labels": labels}


def main():
    os.makedirs(OUT, exist_ok=True)
    ds = J("dataset/flame_runs.json")
    runs = ds["runs"]
    fam = {"solid": "s", "liquid": "d", "gas": "g"}
    pts = []
    for r in runs:
        c, a = r["conditions"], r["conditions"]["atmosphere"]
        if c.get("o2_location") != "ambient" or a["o2_frac"] is None or not a["pressure_kpa"]:
            continue
        pts.append([round(a["pressure_kpa"] / 6.895, 2), round(a["o2_frac"] * 100, 1), fam.get(c["fuel"]["phase"], "g")])
    solid_max = max(p[1] for p in pts if p[2] == "s")
    docs = sum(1 for _ in open(os.path.join(ROOT, "dataset", "documents.jsonl")))
    report_pages = sum(1 for l in open(os.path.join(ROOT, "dataset", "documents.jsonl")) if '"report"' in l)
    pe, sp, em = J("dataset/predict_eval.json"), J("public/station/simparams.json"), J("public/models/flame_emulator.json")
    loo = open(os.path.join(ROOT, "dataset", "loo_eval.md")).read()
    spread = open(os.path.join(ROOT, "dataset", "spread_eval.md")).read()
    fate_loo = [int(x) for x in re.search(r"Solid fate: (\d+) of (\d+)", loo).groups()]
    spread_fit = [int(x) for x in re.search(r"\*\*(\d+) of (\d+)\*\* NASA targets", spread).groups()]
    spread_loo = [int(x) for x in re.search(r"Spread: (\d+) of (\d+)", loo).groups()]
    m = re.search(r"SIBAL fabric concurrent 20 cm/s, 22.1% O2 \| ([\d.]+) mm/s \| burns, ([\d.]+) mm/s", spread)
    sibal = {"nasa": float(m.group(1)), "sim": float(m.group(2))}
    log = [json.loads(l) for l in open(os.path.join(ROOT, "data", "calib", "log.jsonl"))]
    curve = [round(r["best_loss"], 4) for r in log]
    ins, risk = J("public/station/insights.json"), J("public/station/risk.json")
    hab = {}
    for h in ("iss", "moon"):
        it = ins["habitats"][h]["items"]["crew_quarters"]
        hab[h] = {"name": ins["habitats"][h]["name"], "o2": ins["habitats"][h]["o2"], "g": ins["habitats"][h]["gravity_g"],
                  "fans_on": it["fans_on"]["burns"], "fans_off": it["fans_off"]["burns"], "min_o2": it["min_o2_burning_fans_on"],
                  "safe_m": risk["habitats"][h]["fans"]["on"]["objects"]["crew_quarters"]["safe_distance_m"]["p90"]}
    from flame.search import Index
    hit = next(h for h in Index().search("flow abruptly cut off extinguish within 2 s", k=3, investigation="PSI-25")
               if "p. 31" in h["cite"])
    i = hit["text"].find("the flow was abruptly cut off")
    quote = hit["text"][hit["text"].rfind(".", 0, i - 60) + 1: hit["text"].find(".", i) + 1].replace("\n", " ").strip()
    data = {
        "runs": len(runs), "outcomes": sum(r["has_outcome"] for r in runs), "investigations": len(ds["investigations"]),
        "documents": docs, "report_pages": report_pages, "points": pts, "solid_max": solid_max,
        "videos_measured": len([k for k in J("data/frames/measures.json") if not k.startswith("_")]),
        "gas_outcomes": pe["gas_outcome"], "gas_time": pe["gas_extinction_time"], "drop_k": pe["droplet_burning_rate"],
        "drop_ext": pe["droplet_extinction_size"], "fate_loo": fate_loo, "spread_fit": spread_fit, "spread_loo": spread_loo,
        "sibal": sibal, "curve": curve, "sim_test": sp["fit"]["test"], "default_test": sp["website_defaults_fit"]["test"],
        "fate_default": sp["website_defaults_fit"]["solid_fate"], "emulator": em["test"]["accuracy"], "habitats": hab,
        "citation": {"cite": hit["cite"], "quote": quote},
    }
    with open(os.path.join(OUT, "data.json"), "w") as f:
        f.write(json.dumps(data, allow_nan=False))
    # images: a real NASA frame, the matching simulation frame, the burn
    shutil.copy(os.path.join(ROOT, "public", "media", "PSI-25_B8", "thumb.jpg"), os.path.join(OUT, "nasa_b8.jpg"))
    def demo_file(rel):  # the video project's assets live on the demo-video branch: read them from there via git
        path = os.path.join(ROOT, "demo", "public", rel)
        if os.path.exists(path):
            return open(path, "rb").read()
        return subprocess.run(["git", "show", f"demo-video:demo/public/{rel}"], cwd=ROOT, capture_output=True, check=True).stdout
    tmp = os.path.join(OUT, "_sim.mp4")
    open(tmp, "wb").write(demo_file("sim_b8.mp4"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "4", "-i", tmp, "-frames:v", "1", "-q:v", "3",
                    os.path.join(OUT, "sim_b8.jpg")], check=True)
    os.remove(tmp)
    for src, dst in (("i030", "burn_iss.jpg"), ("i070", "burn_iss_out.jpg"), ("m030", "burn_moon.jpg")):
        open(os.path.join(OUT, dst), "wb").write(demo_file(f"burn/{src}.jpg"))
    open(os.path.join(OUT, "flamelab4.mp4"), "wb").write(demo_file("flamelab4.mp4"))
    data["nn"] = nn_assets(em)
    with open(os.path.join(OUT, "data.json"), "w") as f:
        f.write(json.dumps(data, allow_nan=False))
    assert math.isclose(solid_max, 22.2) and data["runs"] == 1624, (solid_max, data["runs"])
    print(f"pitch data: {data['runs']} runs, {len(pts)} points, solid max {solid_max}, fate LOO {fate_loo}, "
          f"tuning {curve[0]} → {curve[-1]} over {len(curve)} rounds, citation {hit['cite']}")


if __name__ == "__main__":
    main()
