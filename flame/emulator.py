"""Neural-network emulator of the (calibrated) flame simulation: conditions → flame image + shape + fate, instantly.

1. Sample conditions over the habitat-relevant space (gravity 0-1 g, O2 12-60 %, 30-300 kPa, airflow 0-40 cm/s,
   4 fuel types), run the simulation for each on the GPU with the calibrated knobs (public/station/simparams.json),
   and record: the average camera image of the last 10 sim-seconds (32 x 24 px), shape measures (flame/shape.py),
   ignited / went out.
2. Train a small MLP (an ensemble of 5, so disagreement = uncertainty) on 90 %, test on 10 %.
3. Export weights as JSON for the browser (public/models/flame_emulator.json, run by public/station/emulator.js).

    python -m flame.emulator --n 20000          # dataset (data/emulator/sims.npz) + training + export
    python -m flame.emulator --train-only
The emulator copies the simulation, errors included: it is as right as flame/shape_eval.py says the simulation is.
"""
import argparse, base64, json, multiprocessing as mp, os, time

import numpy as np
import torch
import torch.nn as nn

from flame.media import ROOT
from flame.shape import clip_measures
from flame.sim import FUELS, Sim, load_theta

DATA = os.path.join(ROOT, "data", "emulator", "sims.npz")
EXPORT = os.path.join(ROOT, "public", "models", "flame_emulator.json")
FUEL_LIST = list(FUELS)
IMG_H, IMG_W = 32, 24
SECONDS, EVERY = 20.0, 0.5
SCALARS = ["ignited", "extinguished", "alive", "aspect", "fill", "hollow", "blue", "flicker"]


def sample(n, rng):
    """Random conditions; a share sits exactly on the common cases (0 g, still air)."""
    out = []
    for _ in range(n):
        g = 0.0 if rng.random() < 0.35 else float(rng.choice([0.166, 0.38, 1.0])) if rng.random() < 0.3 else float(rng.uniform(0, 1))
        out.append(dict(gravity_g=g, o2=float(np.exp(rng.uniform(np.log(0.12), np.log(0.6)))),
                        pressure_kpa=float(np.exp(rng.uniform(np.log(30), np.log(300)))),
                        flow_cm_s=0.0 if rng.random() < 0.25 else float(rng.uniform(0, 40)),
                        fuel=FUEL_LIST[int(rng.integers(len(FUEL_LIST)))], emit=float(np.exp(rng.uniform(np.log(0.5), np.log(3))))))
    return out


def features(c):
    """Condition dict → network input (same order in emulator.js)."""
    return [c["gravity_g"], np.sqrt(c["gravity_g"]), c["o2"] / 0.21, np.log(c["pressure_kpa"] / 101.325),
            c["flow_cm_s"] / 20, np.log(c.get("emit", 1.0)), *[float(c["fuel"] == f) for f in FUEL_LIST]]


def _measure(frames):
    m = clip_measures(frames[4:], skip=0)
    return [m["alive"], m.get("extinguished", False)] + [m.get(k) for k in ("aspect", "fill", "hollow", "blue", "flicker")]


def generate(n, batch=1024, seed=0):
    rng = np.random.default_rng(seed)
    conds = sample(n, rng)
    theta = load_theta()
    X, IMG, S = [], [], []
    with mp.Pool(min(24, os.cpu_count())) as pool:
        for i in range(0, n, batch):
            t0 = time.time()
            chunk = conds[i:i + batch]
            pad = batch - len(chunk)
            sim = Sim(chunk + [chunk[-1]] * pad, theta)
            fr = sim.run(SECONDS, EVERY).numpy()[:len(chunk)]  # (b, t, 128, 96, 3)
            late = fr[:, -int(10 / EVERY):].astype(np.float32).mean(1) / 255  # last 10 s average
            img = torch.nn.functional.avg_pool2d(torch.from_numpy(late).permute(0, 3, 1, 2), 4).permute(0, 2, 3, 1).numpy()
            ms = pool.map(_measure, list(fr))
            for c, im, m in zip(chunk, img, ms):
                alive, ext, *shape = m
                X.append(features(c))
                IMG.append(im)
                S.append([float(alive > 0), float(ext), alive] + [np.nan if v is None else v for v in shape])
            print(f"{i + len(chunk)}/{n} sims  {time.time() - t0:.0f} s", flush=True)
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    np.savez_compressed(DATA, X=np.array(X, np.float32), img=np.array(IMG, np.float16), S=np.array(S, np.float32),
                        conds=json.dumps(conds), theta=json.dumps(theta))


PCS = 48  # image = mean + 48 principal components (shared by all members): small enough for the browser


class Net(nn.Module):
    def __init__(self, d_in, mean, basis, hidden=192):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(d_in, hidden), nn.SiLU(), nn.Linear(hidden, hidden), nn.SiLU(),
                                  nn.Linear(hidden, hidden), nn.SiLU())
        self.img = nn.Linear(hidden, PCS)
        self.sc = nn.Linear(hidden, len(SCALARS))
        self.register_buffer("mean", mean)
        self.register_buffer("basis", basis)

    def forward(self, x):
        h = self.body(x)
        img = (self.mean + self.img(h) @ self.basis).clamp(0, 1)
        return img, self.sc(h)  # scalars: logits for ignited/extinguished, raw for the rest


def loss_fn(img_p, sc_p, img, S):
    li = ((img_p - img) ** 2).mean()
    bce = nn.functional.binary_cross_entropy_with_logits
    lb = bce(sc_p[:, 0], S[:, 0]) + bce(sc_p[:, 1], S[:, 1])
    lit = S[:, 0] > 0.5  # shape measures only exist where there is a flame
    reg = sc_p[:, 2:]
    tgt = S[:, 2:]
    ok = lit.unsqueeze(1) & ~torch.isnan(tgt)
    lr = ((reg - torch.nan_to_num(tgt)) ** 2 * ok).sum() / ok.sum().clamp(min=1)
    return li * 20 + lb + lr


def train(members=3, epochs=400, dev="cuda" if torch.cuda.is_available() else "cpu"):
    d = np.load(DATA)
    X, IMG, S = (torch.tensor(d[k].astype(np.float32)) for k in ("X", "img", "S"))
    # aspect lives on 1..10+: learn log(aspect) so a stretched flame doesn't dominate the loss
    S[:, 3] = torch.log(S[:, 3])
    n = len(X)
    perm = torch.randperm(n, generator=torch.Generator().manual_seed(0))
    te, tr = perm[:n // 10], perm[n // 10:]
    mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
    Xn = (X - mu) / sd
    flat = IMG[tr].flatten(1)
    mean = flat.mean(0)
    _, sv, V = torch.linalg.svd(flat - mean, full_matrices=False)
    basis = V[:PCS]
    print(f"image PCA: {PCS} components keep {float((sv[:PCS] ** 2).sum() / (sv ** 2).sum()):.1%} of the variance", flush=True)
    nets = []
    for m in range(members):
        torch.manual_seed(m)
        net = Net(X.shape[1], mean, basis).to(dev)
        opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
        idx = tr[torch.randint(len(tr), (len(tr),), generator=torch.Generator().manual_seed(100 + m))]  # bootstrap
        Xd, Id, Sd = Xn[idx].to(dev), IMG[idx].to(dev).flatten(1), S[idx].to(dev)
        for ep in range(epochs):
            for b in torch.randperm(len(idx), device=dev).split(512):
                ip, sp = net(Xd[b])
                loss = loss_fn(ip, sp, Id[b], Sd[b])
                opt.zero_grad()
                loss.backward()
                opt.step()
            sched.step()
        nets.append(net.eval())
        print(f"member {m}: train loss {loss.item():.4f}", flush=True)
    # held-out test
    with torch.no_grad():
        outs = [net(Xn[te].to(dev)) for net in nets]
        ip = torch.stack([o[0] for o in outs]).mean(0).cpu()
        sp = torch.stack([o[1] for o in outs]).mean(0).cpu()
        spread = torch.stack([o[1] for o in outs]).std(0).cpu()
    St = S[te]
    img_rmse = float(((ip - IMG[te].flatten(1)) ** 2).mean().sqrt())
    acc = {k: float(((sp[:, i] > 0) == (St[:, i] > 0.5)).float().mean()) for i, k in enumerate(SCALARS[:2])}
    lit = St[:, 0] > 0.5
    errs = {}
    for i, k in enumerate(SCALARS[2:], 2):
        ok = lit & ~torch.isnan(St[:, i])
        e = (sp[ok, i] - St[ok, i]).abs()
        base = (St[ok, i] - St[ok, i].median()).abs()
        errs[k] = {"mae": float(e.mean()), "baseline_mae": float(base.mean()),
                   "spread_error_corr": float(np.corrcoef(spread[ok, i], e)[0, 1]) if ok.sum() > 2 else None}
    rep = {"sims": n, "test": len(te), "image_rmse": img_rmse, "accuracy": acc, "measures": errs,
           "note": "aspect is learned as log(aspect)"}
    export(nets, mu, sd, rep)
    print(json.dumps(rep, indent=1))
    return rep


def export(nets, mu, sd, rep):
    """Weights as base64 float16 per layer (+ the shared image basis), for public/station/emulator.js."""
    b64 = lambda t: base64.b64encode(t.detach().cpu().float().numpy().astype("<f2").tobytes()).decode()
    members = []
    for net in nets:
        layers = [m for m in net.body if isinstance(m, nn.Linear)] + [net.img, net.sc]
        members.append([{"in": l.in_features, "out": l.out_features, "w": b64(l.weight), "b": b64(l.bias)} for l in layers])
    # reference prediction, checked by public/station/emulator.test.mjs (browser code must give the same numbers)
    ref_c = dict(gravity_g=0.166, o2=0.3, pressure_kpa=70.3, flow_cm_s=5.0, fuel="fabric", emit=1.0)
    with torch.no_grad():
        dev = next(nets[0].parameters()).device
        x = ((torch.tensor([features(ref_c)], dtype=torch.float32) - mu) / sd).to(dev)
        outs = [net.half().float()(x) for net in nets]  # float16 round trip, like the export
        ref = {"cond": ref_c, "img_sum": float(sum(o[0] for o in outs).sum() / len(outs)),
               "scalars": (sum(o[1] for o in outs) / len(outs))[0].tolist()}
    os.makedirs(os.path.dirname(EXPORT), exist_ok=True)
    with open(EXPORT, "w") as f:
        json.dump({"inputs": ["gravity_g", "sqrt_g", "o2_rel_air", "log_p_rel_1atm", "flow_per_20cm_s", "log_emit",
                              *[f"fuel_{x}" for x in FUEL_LIST]], "fuels": FUEL_LIST, "mu": mu.tolist(), "sd": sd.tolist(),
                   "img": [IMG_H, IMG_W, 3], "scalars": SCALARS, "members": members, "test": rep,
                   "img_mean": b64(nets[0].mean), "img_basis": b64(nets[0].basis), "pcs": PCS, "reference": ref,
                   "note": "Ensemble MLP emulating flame/sim.py (calibrated). Body: 3 x Linear+SiLU; heads: image "
                           "(PCA coefficients: img = clip(img_mean + coef @ img_basis, 0, 1), row 0 = top) and scalars (ignited/extinguished logits, alive, log aspect, fill, "
                           "hollow, blue, flicker)."}, f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--train-only", action="store_true")
    ap.add_argument("--epochs", type=int, default=400)
    a = ap.parse_args()
    if not a.train_only:
        generate(a.n)
    train(epochs=a.epochs)


if __name__ == "__main__":
    main()
