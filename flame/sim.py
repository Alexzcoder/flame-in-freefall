"""Batched GPU port of the website's flame simulation (public/station/flamelab.js), for evaluation and training.

Same solver step for step: semi-Lagrangian advection, one-step combustion (fuel + O2 -> heat + soot where hot),
buoyancy ~ gravity, fan inflow from the left, vorticity confinement, 24 Jacobi pressure iterations.
Grid 96 x 128 cells, row 0 = bottom (like WebGL uv.y = 0). Every run in a batch has its own conditions, so one call
simulates hundreds of NASA runs (or calibration candidates) at once.

Physics knobs live in THETA (defaults = the website's hand-tuned values). flame/calibrate.py fits them to NASA video
and writes public/station/simparams.json, which flamelab.js reads, so the website runs the calibrated model.

    python -m flame.sim          # self-check: flame lives in 1 g air, dies without oxygen, 0 g droplet flame is round
"""
import json, os

import torch
import torch.nn.functional as F

W, H = 96, 128
FUELS = {  # x0, y0, x1, y1 (fractions of the domain), base fuel release, round source
    "fabric": ((0.38, 0.14, 0.62, 0.17), 2.2, 0),
    "pmma": ((0.40, 0.12, 0.60, 0.20), 0.9, 0),
    "droplet": ((0.4625, 0.29, 0.5375, 0.3463), 7.0, 1),
    "burner": ((0.4625, 0.40, 0.5375, 0.4563), 9.0, 1),
}
THETA = {  # website defaults; calibrate.py changes these
    "k": 16.0, "heat": 1.5, "cool": 0.6, "ign": 0.35, "buoy": 26.0, "dif_o2": 0.22, "dif_fuel": 0.20, "cond": 0.10,
    "flow_scale": 0.9, "eps0": 4.0, "eps_g": 10.0, "emit_scale": 1.0,
    "inv_fuel": 1.0, "inv_o2": 1.0, "cam_blue": 1.0, "cam_soot": 0.7,
    "tad_exp": 0.0,
    "anchor": 0.5,  # temperature the burning surface keeps after the igniter (above "ign" = the flame can never die)
    "emit0": 0.7,   # fuel released by a cold surface (pyrolysis also grows with temperature: + 2.0 * T)  # heat release ~ (adiabatic flame temperature / 2300 K)^tad_exp when a run records it (CFI-G)  # inverse flames: ambient fuel level and burner oxygen release (not on the website)
}
DT = 1 / 60
PARAMS_JSON = os.path.join(os.path.dirname(__file__), "..", "public", "station", "simparams.json")


def load_theta():
    """Calibrated knobs if calibrate.py has written them, else the website defaults."""
    try:
        return {**THETA, **json.load(open(PARAMS_JSON))["theta"]}
    except FileNotFoundError:
        return dict(THETA)


def _nb(x):
    """Neighbours with clamp-to-edge, like a CLAMP_TO_EDGE texture: (left, right, bottom, top)."""
    p = F.pad(x, (1, 1, 1, 1), mode="replicate")
    return p[..., 1:-1, :-2], p[..., 1:-1, 2:], p[..., :-2, 1:-1], p[..., 2:, 1:-1]


def _smooth(a, b, x):
    t = ((x - a) / (b - a)).clamp(0, 1)
    return t * t * (3 - 2 * t)


class Sim:
    """conds: list of dicts {gravity_g, o2 (mole fraction), flow_cm_s, pressure_kpa, fuel, emit (optional multiplier),
    inverse (optional: the source releases oxygen into a fuel atmosphere, CFI-G inverse flames), ambient_fuel (mole
    fraction of fuel around an inverse flame)}."""

    def __init__(self, conds, theta=None, device=None, compile=True):
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        B, d = len(conds), self.dev
        # physics knobs: one dict for all rows, or one dict per row (calibration runs many candidates in one batch)
        rows = theta if isinstance(theta, list) else [theta or {}] * B
        assert len(rows) == B
        self.th = {k: torch.tensor([float({**THETA, **r}[k]) for r in rows], device=d).view(B, 1, 1) for k in THETA}
        col = lambda k, f=float: torch.tensor([f(c[k]) for c in conds], device=d).view(B, 1, 1)
        self.g = col("gravity_g").clamp(min=0)
        self.o2 = col("o2") / 0.21
        self.flow = col("flow_cm_s")
        self.pr = (col("pressure_kpa") / 101.325).clamp(min=0.2)
        fu = [FUELS[c.get("fuel", "fabric")] for c in conds]
        tad = torch.tensor([float(c.get("tad_k") or 2300) for c in conds], device=d).view(B, 1, 1)
        self.heatm = (tad / 2300) ** self.th["tad_exp"]
        self.inv = torch.tensor([bool(c.get("inverse")) for c in conds], device=d).view(B, 1, 1)
        self.amb_fuel = torch.tensor([float(c.get("ambient_fuel") or 0) for c in conds], device=d).view(B, 1, 1) / 0.21
        self.emit = torch.tensor([f[1] * c.get("emit", 1.0) for f, c in zip(fu, conds)], device=d).view(B, 1, 1)
        rect = torch.tensor([f[0] for f in fu], device=d)
        rnd = torch.tensor([f[2] for f in fu], device=d).view(B, 1, 1).bool()
        ys, xs = torch.meshgrid((torch.arange(H, device=d) + 0.5) / H, (torch.arange(W, device=d) + 0.5) / W, indexing="ij")
        self.u, self.v = xs, ys
        ctr, hs = (rect[:, :2] + rect[:, 2:]) / 2, (rect[:, 2:] - rect[:, :2]) / 2
        dx = (xs - ctr[:, 0].view(B, 1, 1)) / hs[:, 0].view(B, 1, 1)
        dy = (ys - ctr[:, 1].view(B, 1, 1)) / hs[:, 1].view(B, 1, 1)
        self.on_fuel = torch.where(rnd, dx * dx + dy * dy < 1, (dx.abs() < 1) & (dy.abs() < 1))
        self.edge = torch.minimum(torch.minimum(xs, 1 - xs), torch.minimum(ys, 1 - ys)) < 0.025
        self.left = 1 - _smooth(0.0, 0.12, xs)
        base = torch.stack([xs, ys], -1) * 2 - 1  # grid_sample coordinates of cell centres
        self.base = base.expand(B, H, W, 2)
        self.B = B
        self.reset()
        if compile and self.dev == "cuda":
            self._core = torch.compile(self._core)

    def reset(self):
        B, d = self.B, self.dev
        self.vel = torch.zeros(B, 2, H, W, device=d)
        self.prs = torch.zeros(B, 1, H, W, device=d)
        self.s = torch.zeros(B, 4, H, W, device=d)  # temperature, fuel vapour, oxygen (1 = cabin level), soot
        self.s[:, 2] = torch.where(self.inv, 0.0, self.o2).expand(B, H, W)
        self.s[:, 1] = torch.where(self.inv, self.amb_fuel * self.th["inv_fuel"], 0.0).expand(B, H, W)
        self.time = 0.0
        self.tt = torch.zeros((), device=self.dev)

    def _advect(self, f, keep):
        off = torch.stack([self.vel[:, 0] / W, self.vel[:, 1] / H], -1) * DT * 2  # cells/s -> grid_sample units
        out = F.grid_sample(f, self.base - off, mode="bilinear", padding_mode="border", align_corners=False)
        return out * torch.tensor(keep, device=self.dev).view(1, -1, 1, 1)

    @torch.no_grad()
    def step(self):
        self.time += DT
        self.tt.fill_(self.time)
        self._core()

    def _core(self):
        th, dt = self.th, DT
        self.vel = self._advect(self.vel, [0.995, 0.995])
        s = self._advect(self.s, [1, 0.99, 1, 0.997])
        T, fu, ox, so = s.unbind(1)
        pr, o2 = self.pr, self.o2
        dif = 1 / pr.sqrt()
        L, R, Bo, To = _nb(s)
        n = L + R + Bo + To
        ox = ox + (n[:, 2] * 0.25 - ox) * (th["dif_o2"] * dif).clamp(max=0.24)
        fu = fu + (n[:, 1] * 0.25 - fu) * (th["dif_fuel"] * dif).clamp(max=0.24)
        T = T + (n[:, 0] * 0.25 - T) * th["cond"]
        surf = torch.where(self.tt < 1.2, 1.2, th["anchor"])  # igniter for the first 1.2 s
        src = dt * self.emit * th["emit_scale"] * (th["emit0"] + 2.0 * T.clamp(max=1.5))
        normal_src, inv_src = self.on_fuel & ~self.inv, self.on_fuel & self.inv
        fu = torch.where(normal_src, fu + src, fu)
        ox = torch.where(inv_src, ox + src * th["inv_o2"], ox)  # inverse flame: oxygen comes out of the burner
        T = torch.where(self.on_fuel, T.clamp(min=surf), T)
        k = th["k"] * o2.clamp(max=2.2) * pr.sqrt()
        r = k * fu * ox * _smooth(th["ign"], th["ign"] + 0.25, T)
        r = torch.minimum(r, torch.minimum(fu, ox) / dt)
        fu, ox = fu - r * dt, ox - r * dt * 0.9
        T = T + r * dt * th["heat"] * self.heatm * (0.6 + 0.4 * o2)
        so = so + r * dt * 0.35
        T = T - dt * th["cool"] * T * T
        e = self.edge
        ox = torch.where(e, (ox + torch.where(self.inv, 0.0, o2)) * 0.5, ox)  # open boundary: fresh ambient
        fu = torch.where(e & self.inv, (fu + self.amb_fuel * th["inv_fuel"]) * 0.5, fu)
        T, so = torch.where(e, T * 0.5, T), torch.where(e, so * 0.8, so)
        self.s = torch.stack([T, fu, ox, so], 1).clamp(min=0)
        self.rate = r  # reaction rate this step (heat release map)

        # forces
        vx, vy = self.vel.unbind(1)
        L, R, Bo, To = _nb(self.vel)
        curl = 0.5 * (R[:, 1] - L[:, 1] - To[:, 0] + Bo[:, 0])
        g = self.g
        vy = vy + dt * th["buoy"] * g * pr.sqrt() * (T - 0.05 * so)
        flow = self.flow * th["flow_scale"]
        vx = vx + (flow - vx) * dt * 0.8 * self.left + (flow - vx) * dt * 0.05
        cL, cR, cB, cT = _nb(curl.unsqueeze(1))
        gx, gy = cT[:, 0].abs() - cB[:, 0].abs(), cR[:, 0].abs() - cL[:, 0].abs()
        ln = (gx * gx + gy * gy).sqrt() + 1e-5
        eps = th["eps0"] + th["eps_g"] * g.sqrt()
        vx, vy = vx + dt * eps * gx / ln * curl, vy - dt * eps * gy / ln * curl
        self.vel = torch.stack([vx, vy], 1)
        # pressure projection
        L, R, Bo, To = _nb(self.vel)
        div = (0.5 * (R[:, 0] - L[:, 0] + To[:, 1] - Bo[:, 1])).unsqueeze(1)
        p = self.prs
        for _ in range(24):
            pl, pR, pb, pt = _nb(p)
            p = (pl + pR + pb + pt - div) * 0.25
        self.prs = p
        pl, pR, pb, pt = _nb(p)
        self.vel = self.vel - 0.5 * torch.cat([pR - pl, pt - pb], 1)

    def render(self, mode="camera"):
        """RGB image (B, H, W, 3) in 0..1, row 0 = TOP (image order).
        camera: light a camera would see: blue chemiluminescence where it reacts + yellow-orange glowing soot where
                hot (soot * T^4). Used for measuring. website: the website's `show` shader (hot gas glows too)."""
        T, fu, ox, so = self.s.unbind(1)
        if mode == "camera":
            th = self.th
            ch = (self.rate * th["cam_blue"]).clamp(0, 1).unsqueeze(-1)
            glow = (so * T ** 4 * th["cam_soot"] * _smooth(0.5, 0.9, T)).clamp(0, 1).unsqueeze(-1)
            dev = self.dev
            col = ch * torch.tensor([0.25, 0.35, 1.0], device=dev) + glow * torch.tensor([1.0, 0.55, 0.15], device=dev)
            return (col.clamp(0, 1) ** 0.85 + 0.018).clamp(0, 1).flip(1)
        blue = (1 - self.g * 3).clamp(min=0)
        t = T.clamp(0, 2)
        fire = torch.stack([1.6 * t, 1.1 * t * t, 0.55 * t ** 3], -1)
        zone = (16.0 * fu * ox * _smooth(0.35, 0.6, T) * 0.45).clamp(0, 1).unsqueeze(-1)
        b = blue.unsqueeze(-1)
        col = fire * (1 - 0.55 * b) + torch.tensor([0.18, 0.42, 1.0], device=self.dev) * zone * (0.35 + 1.1 * b)
        sm = (so * 0.35).clamp(0, 0.7).unsqueeze(-1)
        col = col * (1 - sm) + (col * 0.4 + 0.07) * sm
        col = col.clamp(min=0) ** 0.85 + torch.tensor([0.018, 0.022, 0.035], device=self.dev)
        return col.clamp(0, 1).flip(1)

    def run(self, seconds=10.0, every=0.5, mode="camera"):
        """Simulate; return rendered frames sampled every `every` sim-seconds, (B, n, H, W, 3) on CPU as uint8."""
        frames, nxt = [], every
        for _ in range(int(round(seconds / DT))):
            self.step()
            if self.time + 1e-9 >= nxt:
                frames.append((self.render(mode) * 255).to(torch.uint8).cpu())
                nxt += every
        return torch.stack(frames, 1)


    def run_alive(self, seconds=30.0, every=0.5, min_cells=4, lum=0.12):
        """Cheap path for outcomes: is there a visible flame (camera render) at each sample time? → (B, n) bool, times."""
        alive, times, nxt = [], [], every
        for _ in range(int(round(seconds / DT))):
            self.step()
            if self.time + 1e-9 >= nxt:
                alive.append(((self.render("camera").mean(-1) > lum).sum((1, 2)) >= min_cells).cpu())
                times.append(self.time)
                nxt += every
        return torch.stack(alive, 1).numpy(), times


def _check():
    conds = [dict(gravity_g=1, o2=0.21, flow_cm_s=0, pressure_kpa=101.325, fuel="fabric"),
             dict(gravity_g=1, o2=0.0, flow_cm_s=0, pressure_kpa=101.325, fuel="fabric"),
             dict(gravity_g=0, o2=0.21, flow_cm_s=0, pressure_kpa=101.325, fuel="droplet")]
    sim = Sim(conds)
    f = sim.run(6, 1.0, mode="website")[:, -1].float() / 255  # last frame
    lum = f.mean(-1)
    lit = lum > 0.4  # warm non-burning gas renders dim orange; flames are brighter
    assert lit[0].sum() > 50, "1 g flame in air should be burning"
    fuel_cells = int(sim.on_fuel[1].sum())
    assert lit[1].sum() <= fuel_cells * 1.6, f"no oxygen: only the hot fuel surface glows ({int(lit[1].sum())} vs {fuel_cells})"
    assert lit[0].sum() > 3 * fuel_cells, "1 g flame should be much bigger than its fuel strip"
    ys, xs = torch.nonzero(lit[2], as_tuple=True)
    assert len(xs) > 20, "0 g droplet flame should be burning"
    ar = (xs.float().std() / ys.float().std()).item()
    assert 0.7 < ar < 1.4, f"0 g still-air droplet flame should be round, aspect {ar:.2f}"
    ys0 = torch.nonzero(lit[0], as_tuple=True)[0]
    assert ys0.float().mean() < H * (1 - 0.17), "1 g flame should rise above the fuel strip"
    print(f"sim ok on {sim.dev}: 1 g lit cells {int(lit[0].sum())}, droplet aspect {ar:.2f}")


if __name__ == "__main__":
    _check()
