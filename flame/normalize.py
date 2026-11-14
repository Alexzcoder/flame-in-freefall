"""Raw PSI run tables -> one Dataset in the shared schema (flame/schema.py).

    python -m flame.normalize        # reads data/raw/, writes dataset/flame_runs.json + .csv

One Normalizer subclass per run table. Each maps a raw CSV row to a Run, or None to skip it.
Rule: values we can't read unambiguously become null (raw text kept in `extra`), never guessed.
"""
import csv, dataclasses, io, json, os, re
from datetime import datetime

from .schema import Atmosphere, Conditions, Dataset, Flow, Fuel, Ignition, Investigation, Outcome, Run, Source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "dataset", "flame_runs.json")

MMHG, ATM, BAR = 0.133322368, 101.325, 100.0  # -> kPa
# Cabin air for experiments run in the ISS Microgravity Science Glovebox or the Cygnus cabin when the table doesn't
# record it. Always listed in run.assumed so it is never mistaken for a measurement.
CABIN_KPA, CABIN_O2 = 101.325, 0.21
P_PATH, O2_PATH = "conditions.atmosphere.pressure_kpa", "conditions.atmosphere.o2_frac"
BASS_U_PER_AIR = 1.0066  # cm/s per 'Air display' unit, PSI-25 Reference Data/Fan calibration data.xlsx
INCH = 25.4
MEDIA_EXT = {".mp4", ".ts", ".avi", ".mov", ".zip", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".nef"}


# ---------- small parsers (return None when the text isn't a clean value) ----------
def num(s):
    """'757.7' -> 757.7; '~ 21.5' -> 21.5; '' / 'n/a' / 'RAMPED' / '0.9 1.3' -> None."""
    s = str(s).strip().lstrip("~").strip()
    try:
        return float(s)
    except ValueError:
        return None


def mid(s):
    """Point value or range midpoint: '21.5 - 21.7' / '22.1 to 22.0' / '~ 21.5' -> float."""
    m = re.fullmatch(r"~?\s*(-?\d*\.?\d+)\s*(?:-|to)\s*(-?\d*\.?\d+)", str(s).strip())
    return (float(m[1]) + float(m[2])) / 2 if m else num(s)


def with_unit(s, units):
    """'0.27 mm' -> value in mm given units={'mm':1,'cm':10}; bare numbers are rejected (ambiguous)."""
    m = re.fullmatch(r"~?\s*(\d*\.?\d+)\s*([a-zA-Z/]+)", str(s).strip())
    if not m or m[2] not in units:
        return None
    if m[1].startswith("0") and not m[1].startswith("0.") and m[1] != "0":
        return None  # '037 mm': leading-zero typo, could be 0.37 or 37 -> unknown
    return float(m[1]) * units[m[2]]


def date(s, *fmts):
    for f in fmts:
        try:
            return datetime.strptime(s.strip(), f).date().isoformat()
        except ValueError:
            pass
    return None


def mul(x, k):
    return None if x is None else x * k


def frac(pct):
    return None if pct is None else round(pct / 100, 5)


def rnd(x, n=4):
    return None if x is None else round(x, n)


# ---------- base class ----------
class Normalizer:
    acc = ""        # "PSI-69"
    table = ""      # file name suffix after "PSI-xx_Experimental table_"

    @property
    def file(self):
        return f"{self.acc}_Experimental table_{self.table}.csv"

    def rows(self):
        raw = open(os.path.join(RAW, "run_tables", self.file), "rb").read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
        rows = list(csv.reader(io.StringIO(text)))
        head = [re.sub(r"\s+", " ", h).strip() for h in rows[0]]
        for i, r in enumerate(rows[1:], start=1):
            if any(c.strip() for c in r):
                yield i, {h: (r[j].strip() if j < len(r) else "") for j, h in enumerate(head)}

    def to_run(self, i, r):
        raise NotImplementedError

    def runs(self, media=None):
        out, seen = [], {}
        self.dropped = 0
        for i, r in self.rows():
            run = self.to_run(i, r)
            if run is None:
                continue
            run.investigation = self.acc
            run.has_outcome = any(v is not None for k, v in dataclasses.asdict(run.outcome).items() if k != "censored")
            if run.id in seen:
                if seen[run.id] == run:  # exact copy of an earlier row (CFI has 8): spreadsheet duplicate, drop
                    self.dropped += 1
                    continue
                run.extra["duplicate_of"] = run.id  # same id, different data (FLEX 193F001 = tests #70 and #73)
                run.id = f"{run.id}~row{i}"
            seen[run.id] = dataclasses.replace(run)
            run.source = Source(self.file, i)
            if media is not None:
                run.media = media.match(self.acc, run.id.split("~")[0].split("/", 1)[1])
            out.append(run)
        return out


class MediaIndex:
    """Links runs to PSI media files whose name contains the test id (e.g. ..._TEST_B1.mp4, ..._21242A1.ts)."""

    def __init__(self):
        self.files = {}

    def _names(self, acc):
        if acc not in self.files:
            d = json.load(open(os.path.join(RAW, "manifests", f"{acc}.json")))
            names = set()

            def walk(o):
                if isinstance(o, dict):
                    if "file_name" in o and "file_size" in o:
                        names.add(o["file_name"])
                        return
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
            walk(d)
            # PSI lists most files twice: "X.zip" (legacy) and "PSI-25_Raw Data_X.zip"; keep the prefixed one
            prefixed = {m[1] for n in names if (m := re.match(rf"{acc}_[^_]+_(.*)$", n))}
            self.files[acc] = sorted(n for n in names if os.path.splitext(n)[1].lower() in MEDIA_EXT
                                     and not (not n.startswith(acc + "_") and n in prefixed))
        return self.files[acc]

    def match(self, acc, test_id):
        if len(test_id) < 3 or test_id.isdigit():  # "S1" / row numbers are too generic to match safely
            return []
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(test_id) + r"(?![0-9])", re.I)
        return [n for n in self._names(acc) if pat.search(n.replace(" ", ""))]


# ---------- droplets ----------
class Flex(Normalizer):
    acc, table = "PSI-69", "FLEX"
    END = {"Disruption": "disruption", "Extinction": "extinction", "Completion": "burnout"}

    def to_run(self, i, r):
        return Run(
            id=f"{self.acc}/{r['FLEX Identifier']}",
            investigation=self.acc, date=date(r["Test Date"], "%m/%d/%Y"),
            conditions=Conditions(
                fuel=Fuel(name=r["Fuel"].lower(), phase="liquid", geometry="droplet", diameter_mm=num(r["Droplet initial diameter; mm"])),
                atmosphere=Atmosphere(
                    o2_frac=num(r["O initial ambient composition; mole fraction"]),
                    n2_frac=num(r["N initial ambient composition; mole fraction"]),
                    co2_frac=num(r["CO initial ambient composition; mole fraction"]),
                    he_frac=num(r["He initial ambient composition; mole fraction"]),
                    pressure_kpa=rnd(mul(num(r["Ambient pressure; mmHg"]) or None, MMHG), 3)),  # 0 mmHg in source = not recorded
                flow=Flow(velocity_cm_s=0.0, direction="quiescent")),
            outcome=Outcome(
                ignited=True, result=self.END.get(r["Test end"]), censored=r["Test end"] == "Disruption",
                burn_time_s=num(r["Burn time; s"]),
                burning_rate_mm2_s=num(r["Burning rate; mm"]),
                extinction_diameter_mm=num(r["Visible flame extinction diameter; mm"])),
            extra={"flex_test_no": int(r["FLEX Test #"]), "gmt": r["Test GMT"], "pressure_raw_mmhg": r["Ambient pressure; mmHg"],
                   "note": "burning_rate from column 'Burning rate; mm', read as d^2-law K [mm^2/s]"})


class Cfi(Normalizer):
    acc, table = "PSI-39", "CFI"

    def to_run(self, i, r):
        fuel = r["Fuel"]
        m = re.match(r"\[\.?(\d+)\]/\[\.?(\d+)\]", fuel)
        p = with_unit(r["Pressure"], {"atm": ATM})
        return Run(
            id=f"{self.acc}/{r['CIR']}", investigation=self.acc, date=date(r["Test Date"], "%d-%b-%y"),
            conditions=Conditions(
                fuel=Fuel(name="n-dodecane" if fuel == "C12H26" else "n-dodecane/iso-dodecane", phase="liquid", geometry="droplet",
                          fuel_frac=float("0." + m[1]) if m else (1.0 if fuel == "C12H26" else None)),
                atmosphere=Atmosphere(o2_frac=num(r["Oxygen"]), n2_frac=num(r["Nitrogen"]), he_frac=num(r["Helium"]),
                                      pressure_kpa=rnd(p, 3)),
                flow=Flow(velocity_cm_s=0.0, direction="quiescent")),
            extra={"flex_number": r["Flex Number"], "fiber_supported": {"Yes": True, "No": False}.get(r["Fiber"]),
                   "fuel_raw": fuel, "note": "fuel_frac = n-dodecane share of the liquid blend; table has no outcome columns"})


# ---------- gaseous (ACME spherical burner) ----------
GAS = {"C2H4": "ethylene", "C3H8": "propane", "ethane": "ethane", "propane": "propane", "butane": "butane"}


class FlameDesignNormal(Normalizer):
    acc, table = "PSI-10", "Flame Design_Normal Flame"

    def to_run(self, i, r):
        return Run(
            id=f"{self.acc}/{r['Test']}", investigation=self.acc,
            conditions=Conditions(
                fuel=Fuel(name=GAS[r["Fuel"]], phase="gas", geometry="spherical_burner",
                          flow_mg_s=rnd(num(r["mfuel (mg/s)"])), fuel_frac=rnd(num(r["Xfuel"]))),
                atmosphere=Atmosphere(o2_frac=rnd(num(r["XO2 (init)"])), pressure_kpa=rnd(mul(num(r["pmean (atm)"]), ATM), 3)),
                flow=Flow(velocity_cm_s=0.0, direction="quiescent")),
            extra={"flame_type": "normal", "day": r["Day"], "ramped": r["Xfuel"] == "RAMPED",
                   "mN2_mg_s": num(r["mN2 (mg/s)"]), "o2_frac_final": rnd(num(r["XO2 (final)"])),
                   "zst": rnd(num(r["mean Zst"])), "tad_k": rnd(num(r["Tad (K)"]), 1)})


class FlameDesignInverse(Normalizer):
    acc, table = "PSI-10", "Flame Design_Inverse Flame"

    def to_run(self, i, r):
        return Run(
            id=f"{self.acc}/{r['Test']}", investigation=self.acc,
            conditions=Conditions(
                fuel=Fuel(name="ethylene", phase="gas", geometry="spherical_burner", fuel_frac=rnd(num(r["XC2H4 initial"]))),
                atmosphere=Atmosphere(o2_frac=rnd(num(r["XO2"])), pressure_kpa=rnd(mul(num(r["pmean (atm)"]), ATM), 3)),
                flow=Flow(velocity_cm_s=0.0, direction="quiescent"), o2_location="burner_stream"),
            extra={"flame_type": "inverse", "day": r["Day"], "mO2_mg_s": num(r["mO2 (mg/s)"]), "mN2_mg_s": num(r["mN2 (mg/s)"]),
                   "zst": rnd(num(r["mean Zst"])), "tad_k": rnd(num(r["Tad (K)"]), 1),
                   "note": "inverse flame: o2_frac is the oxidizer stream from the burner, fuel_frac is the ambient fuel"})


def _cfig_fuel(s):
    m = re.fullmatch(r"(\d+)%\s*(\w+)", s)
    return (m[2], float(m[1]) / 100) if m else (s, None)


def _cfig_outcome(ignited, end, burn):
    """SE = self-extinguished (natural), FT = flow terminated by operator (burn time is a lower bound)."""
    if ignited is False:
        return Outcome(ignited=False, result="no_ignition", burn_time_s=num(burn))
    result = {"SE": "extinction", "FT": "terminated"}.get(end)
    return Outcome(ignited=ignited, result=result, burn_time_s=num(burn),
                   censored={"extinction": False, "terminated": True}.get(result))


class CfigNormal(Normalizer):
    acc, table = "PSI-159", "CFI-G_Normal Flames"

    def to_run(self, i, r):
        name, _ = _cfig_fuel(r["Fuel"])
        cool = r["Cool flame?"].lower()
        return Run(
            id=f"{self.acc}/{r['Test'].replace(' ', '')}", investigation=self.acc,
            conditions=Conditions(
                fuel=Fuel(name=GAS[name], phase="gas", geometry="spherical_burner", flow_mg_s=num(r["mHC (mg/s)"]), fuel_frac=num(r["Xf"])),
                atmosphere=Atmosphere(o2_frac=rnd(num(r["XO2 before test"])), pressure_kpa=rnd(mul(num(r["approx p (bar)"]), BAR), 3)),
                flow=Flow(velocity_cm_s=0.0, direction="quiescent")),
            outcome=_cfig_outcome({"yes": True, "no": False}.get(r["Hot ignition"].lower()), r["Self-ext or flow term"], r["burn time (sec)"]),
            extra={"flame_type": "normal", "day": r["Day"], "cool_flame": True if cool.startswith("yes") else False if cool.startswith("no") else None,
                   "cool_flame_raw": r["Cool flame?"], "tfp": r["TFP"], "zst": rnd(num(r["Zst"])), "tad_k": rnd(num(r["Tad (K)"]), 1),
                   "peak_burner_t_c": rnd(num(r["Peak burner T (C )"]), 1), "comments": r["Comments"]})


class CfigInverse(Normalizer):
    acc, table = "PSI-159", "CFI-G_Inverse Flames"

    def to_run(self, i, r):
        hot = r["Hot ignition"].lower()
        return Run(
            id=f"{self.acc}/{r['Test'].replace(' ', '')}", investigation=self.acc,
            conditions=Conditions(
                fuel=Fuel(name=GAS[r["Fuel"]], phase="gas", geometry="spherical_burner", fuel_frac=rnd(num(r["Xf before test"]))),
                atmosphere=Atmosphere(o2_frac=num(r["XO2"]), pressure_kpa=rnd(mul(num(r["approx p (bar)"]), BAR), 3)),
                flow=Flow(velocity_cm_s=0.0, direction="quiescent"), o2_location="burner_stream"),
            outcome=_cfig_outcome({"yes": True, "no": False, "flash": True}.get(hot), r["Self -ext or flow term"], r["burn time (sec)"]),
            extra={"flame_type": "inverse", "day": r["Day"], "flash_only": hot == "flash", "o2_flow_mg_s": num(r["O2 flow rate (mg/s)"]),
                   "hc_burnrate_mg_s": num(r["HC burnrate (mg/s)"]), "tfp": r["TFP"], "zst": rnd(num(r["Zst"])), "tad_k": rnd(num(r["Tad (K)"]), 1),
                   "peak_burner_t_k": num(r["Peak burner temp (K)"]), "color": r["Color"], "comments": r["Comments"],
                   "note": "inverse flame: o2_frac is the oxidizer stream from the burner, fuel_frac is the ambient fuel"})


class Spice(Normalizer):
    acc, table = "PSI-107", "Spice"

    def to_run(self, i, r):
        m = re.fullmatch(r"(?:(\d+)\s*%\s*)?(\w+)", r["Fuel"])
        t0, t1 = r["GMT ignition"], r["GMT Flame Off"]
        dur = None
        if re.fullmatch(r"\d+:\d\d:\d\d", t0) and re.fullmatch(r"\d+:\d\d:\d\d", t1):
            s = lambda t: sum(int(x) * k for x, k in zip(t.split(":"), (3600, 60, 1)))
            dur = (s(t1) - s(t0)) % 86400
        return Run(
            id=f"{self.acc}/{i}", investigation=self.acc,
            conditions=Conditions(
                fuel=Fuel(name=m[2].lower() if m else r["Fuel"].lower(), phase="gas", geometry="jet",
                          diameter_mm=num(r["Nozzle (mm)"]), flow_mg_s=num(r["Fuel Rate (mg/s)"]),
                          fuel_frac=float(m[1]) / 100 if m and m[1] else 1.0 if m else None),
                atmosphere=Atmosphere(o2_frac=CABIN_O2, pressure_kpa=CABIN_KPA),
                flow=Flow(velocity_cm_s=v if (v := num(r["Air Rate (cm/s)"])) is None or v >= 0 else None, direction="coflow")),  # <0 = sensor offset
            assumed=[O2_PATH, P_PATH],
            extra={"gmt_day": r["GMT date"], "air_rate_raw": r["Air Rate (cm/s)"], "gmt_ignition": t0, "gmt_flame_off": t1, "flame_on_s": dur,
                   "fuel_rate_sccm": num(r["Fuel Rate (sccm)"]), "hc_fuel_rate_mg_s": num(r["HC Fuel Rate (mg/s)"]),
                   "note": "smoke-point study; flame_on_s is operator-controlled, not a natural burn time"})


# ---------- solids ----------
def _bass2_fuel(s):
    t = s.lower()
    name = "pmma" if ("pmma" in t or "rod" in t or "film" in t or "micron" in t) else "sibal" if "sibal" in t else \
        "nomex" if "nomex" in t else "candle wax" if "wax" in t else "unknown"
    geo = "rod" if "rod" in t else "film" if ("film" in t or "micron" in t) else "fabric" if name in ("sibal", "nomex") else \
        "other" if "spherical" in t or "candle" in t else "sheet"
    thick = width = diam = None
    if m := re.search(r"(\d+)\s*micron", t):
        thick = int(m[1]) / 1000
    elif m := re.search(r"(\d*\.?\d+)\s*mm", t):
        thick = float(m[1])
    if m := re.search(r"(\d+)\s*cm", t):
        width = float(m[1]) * 10
    if geo == "rod" and (m := re.search(r"(\d+)/(\d+)", t) or re.search(r"(0\.5)\"", t)):
        diam = (int(m[1]) / int(m[2]) if m.lastindex == 2 else float(m[1])) * INCH
    return Fuel(name=name, phase="solid", geometry=geo, thickness_mm=thick, width_mm=None if geo in ("rod", "other") else width,
                diameter_mm=rnd(diam, 3))


def _bass2_air(text):
    """'Air display' cell -> (initial velocity cm/s, Outcome). The cell logs the flow settings used during the burn,
    e.g. '5', '10   5  4  3  2  1', '5 down to ext', '10   blowoff', 'no ign at any flow'."""
    t = text.lower()
    toks = re.findall(r"\d*\.?\d+", t)
    first = float(toks[0]) if toks and re.match(r"\s*\d", t) else None
    # ponytail: cells with fan readings in brackets ('49 44 42 (5 2 0)') or values > 40 aren't air-display units
    u = round(first * BASS_U_PER_AIR, 2) if first is not None and first <= 40 and "(" not in t else None
    if "no ign" in t:
        out = Outcome(ignited=False, result="no_ignition")
    elif re.search(r"\bext", t) or "blowoff" in t:
        out = Outcome(ignited=True, result="extinction", censored=False)
    elif "ign" in t:
        out = Outcome(ignited=True)
    else:
        out = Outcome()
    return u, out


class Bass2(Normalizer):
    acc, table = "PSI-25", "BASS-II"

    def to_run(self, i, r):
        u, out = _bass2_air(r["Air display"])
        return Run(
            id=f"{self.acc}/{r['Test #']}", investigation=self.acc, date=date(r["Date"], "%m/%d/%Y"),
            conditions=Conditions(
                fuel=_bass2_fuel(r["Fuel Sample Material"]),
                atmosphere=Atmosphere(o2_frac=frac(num(r["Calibrated initial O2 % by vol"])), co2_frac=frac(num(r["Initial CO2 % by vol"])),
                                      pressure_kpa=CABIN_KPA),
                flow=Flow(velocity_cm_s=u)),
            outcome=out, assumed=[P_PATH],
            extra={"pi": r["PI"], "sample": r["Sample #"], "material_raw": r["Fuel Sample Material"],
                   "flow_restrictor": r["Flow restrictor"], "fan_display": r["Fan display"], "air_display": r["Air display"],
                   "extinction_mode": "blowoff" if "blowoff" in r["Air display"].lower() else None,
                   "o2_frac_final": frac(num(r["Calibrated final O2 % by vol"])), "co2_frac_final": frac(num(r["Final CO2 % by vol"])),
                   "co_ppm_initial": num(r["Initial CO (ppm)"]), "co_ppm_final": num(r["Final CO (ppm)"]),
                   "note": "velocity_cm_s = 1.0066 x first 'Air display' value (fan calibration sheet); the display often "
                           "steps down during a burn, see air_display. Flow direction depends on sample mount: not in table."})


CM = {"cm": 10.0, "mm": 1.0}


class Saffire1(Normalizer):
    acc, table = "PSI-98", "SAFFIRE-1"

    def to_run(self, i, r):
        if not r["Sample Number"].startswith("S"):
            return None  # flow-visualisation rows
        bt = num(r["Burn Time (s)"])
        return Run(
            id=f"{self.acc}/{r['Sample Number']}", investigation=self.acc,
            conditions=Conditions(
                fuel=Fuel(name="sibal", phase="solid", geometry="fabric", thickness_mm=mul(num(r["Sample Thickness (cm)"]), 10),
                          length_mm=mul(num(r["Sample Length (cm)"]), 10), width_mm=mul(num(r["Sample Width (cm)"]), 10)),
                atmosphere=Atmosphere(o2_frac=frac(mid(r["Percent O2"])), pressure_kpa=CABIN_KPA),
                flow=Flow(velocity_cm_s=num(r["Air Flow (cm/s)"]), direction=r["Flow Direction"].lower()),
                ignition=Ignition(power_w=num(r["Ignition Power (W)"]), duration_s=num(r["Ignition Time (s)"]))),
            outcome=Outcome(ignited=True if bt else None, burn_time_s=bt), assumed=[P_PATH],
            extra={"o2_raw": r["Percent O2"], "cameras": [r["Camera 1"], r["Camera 2"]]})


class Saffire2(Normalizer):
    acc, table = "PSI-99", "SAFFIRE-2"
    MAT = {"Silicone": "silicone", "Cotton-Fiberglass (SIBAL)": "sibal", "PMMA": "pmma", "PMMA & Nomex": "pmma+nomex"}

    def to_run(self, i, r):
        if not re.fullmatch(r"2-\d", r["Sample Number"]):
            return None  # flow-visualisation rows and footnotes
        bt = with_unit(r["Burn Time (s)"], {"s": 1.0})
        spread = with_unit(r["?-g Spread Length"], {"mm/s": 1.0})
        return Run(
            id=f"{self.acc}/{r['Sample Number']}", investigation=self.acc,
            conditions=Conditions(
                fuel=Fuel(name=self.MAT.get(r["Material"], "unknown"), phase="solid", geometry="sheet",
                          thickness_mm=with_unit(r["Samle Thickness"], CM), length_mm=with_unit(r["Sample Length"], CM),
                          width_mm=with_unit(r["Sample Width (cm)"], CM)),
                atmosphere=Atmosphere(o2_frac=frac(mid(r["Percent O2 (Note 1)"])), pressure_kpa=CABIN_KPA),
                flow=Flow(velocity_cm_s=with_unit(r["Air Flow (cm/s)"], {"cm/s": 1.0}), direction=r["Flow Direction"].lower()),
                ignition=Ignition(power_w=with_unit(r["Ignition Power (W)"], {"W": 1.0}), duration_s=with_unit(r["Ignition Time (s)"], {"s": 1.0}))),
            outcome=Outcome(ignited=True if bt else None, burn_time_s=bt, spread_rate_mm_s=spread), assumed=[P_PATH],
            extra={"material_raw": r["Material"], "thickness_raw": r["Samle Thickness"], "burn_time_raw": r["Burn Time (s)"],
                   "ug_burn_length_raw": r["?-g Burn Length"], "ug_spread_raw": r["?-g Spread Length"],
                   "1g_burn_length_raw": r["1-g Burn Length"], "1g_spread_rate_raw": r["1-g Spread Rate"],
                   "note": "'?-g' columns are microgravity; 1-g columns are the ground comparison test. See table footnotes in source."})


class Saffire3(Normalizer):
    acc, table = "PSI-100", "SAFFIRE-3"

    def to_run(self, i, r):
        return Run(
            id=f"{self.acc}/{r['Sample Number']}", investigation=self.acc,
            conditions=Conditions(
                fuel=Fuel(name="sibal", phase="solid", geometry="fabric", thickness_mm=with_unit(r["Sample Thickness"], CM),
                          length_mm=with_unit(r["Sample Length"], CM), width_mm=with_unit(r["Sample Width"], CM)),
                atmosphere=Atmosphere(o2_frac=CABIN_O2, pressure_kpa=CABIN_KPA),
                flow=Flow(velocity_cm_s=with_unit(r["Air Flow"], {"cm/s": 1.0}), direction=r["Direction"].lower())),
            assumed=[O2_PATH, P_PATH], extra={"cameras": [r["Camera 1"], r["Camera 2"]]})


NORMALIZERS = [Flex(), Cfi(), FlameDesignNormal(), FlameDesignInverse(), CfigNormal(), CfigInverse(), Spice(),
               Bass2(), Saffire1(), Saffire2(), Saffire3()]

CATEGORY = {"PSI-69": "droplet", "PSI-68": "droplet", "PSI-39": "droplet", "PSI-117": "droplet",
            "PSI-10": "gaseous", "PSI-159": "gaseous", "PSI-20": "gaseous", "PSI-21": "gaseous", "PSI-22": "gaseous",
            "PSI-23": "gaseous", "PSI-107": "gaseous", "PSI-106": "gaseous", "PSI-60": "gaseous", "PSI-142": "gaseous",
            "PSI-25": "solid", "PSI-26": "solid", "PSI-98": "solid", "PSI-99": "solid", "PSI-100": "solid", "PSI-62": "solid",
            "PSI-102": "smoke", "PSI-101": "smoke", "PSI-115": "smoke", "PSI-47": "smoke"}
SKIPPED = {
    "PSI-68": "FLEX-2 run table lists condition ranges per fuel, not individual runs",
    "PSI-26": "BASS-I run table has only date/sample/material, no test conditions",
    "PSI-20": "ACME BRE run table has one row per test day, not per flame",
    "PSI-21": "ACME CLD run table has one row per test day, not per flame",
    "PSI-22": "ACME E-FIELD run table has one row per test day, not per flame",
    "PSI-23": "ACME s-Flame run table has one row per test day, not per flame",
    "PSI-106": "SLICE run table is a fuel log (date + fuel) only",
    "PSI-102": "SAME studied smoke from overheated materials (no flames), so its results are in the reports, not the fire run table",
    "PSI-101": "SAME-R studied smoke from overheated materials (no flames), so its results are in the reports, not the fire run table",
    "PSI-47": "DAFT is dust sampling for smoke detectors, not combustion runs",
    "PSI-142": "table indexes figures in papers, not runs",
}


def investigations(normalized):
    out = []
    for f in sorted(os.listdir(os.path.join(RAW, "manifests"))):
        d = json.load(open(os.path.join(RAW, "manifests", f)))
        acc = d["accession"]
        out.append(Investigation(
            id=acc, acronym=d.get("investigationAcronym") or acc, title=d.get("title", ""), category=CATEGORY.get(acc, "other"),
            hardware=d.get("experimentHardware") or None, platform=d.get("flightProgram") or None, doi=d.get("doi") or None,
            objective=d.get("objective") or None, normalized=acc in normalized,
            note=SKIPPED.get(acc) or (None if acc in normalized else "no run table (modelling/analysis study or documents only)"),
            publications=[{"title": p.get("title", ""), "doi": p.get("doi") or None} for p in d.get("publications") or []]))
    return sorted(out, key=lambda x: int(x.id.split("-")[1]))


def build():
    media = MediaIndex()
    runs = [run for n in NORMALIZERS for run in n.runs(media)]
    ds = Dataset(investigations=investigations({n.acc for n in NORMALIZERS}), runs=runs)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    ds.to_json(OUT)
    ds.to_frame().to_csv(OUT.replace(".json", ".csv"), index=False)
    return ds


SOURCE_CHECKS = {  # (raw column, run field path, factor): re-read independently with pandas and compared
    "PSI-69": [("Ambient pressure; mmHg", P_PATH, MMHG), ("O initial ambient composition; mole fraction", O2_PATH, 1),
               ("Droplet initial diameter; mm", "conditions.fuel.diameter_mm", 1), ("Burn time; s", "outcome.burn_time_s", 1),
               ("Burning rate; mm", "outcome.burning_rate_mm2_s", 1),
               ("Visible flame extinction diameter; mm", "outcome.extinction_diameter_mm", 1)],
    "PSI-39": [("Oxygen", O2_PATH, 1), ("Helium", "conditions.atmosphere.he_frac", 1)],
    "PSI-10": [("XO2 (init)", O2_PATH, 1), ("XO2", O2_PATH, 1), ("pmean (atm)", P_PATH, ATM), ("mfuel (mg/s)", "conditions.fuel.flow_mg_s", 1)],
    "PSI-159": [("XO2 before test", O2_PATH, 1), ("XO2", O2_PATH, 1), ("approx p (bar)", P_PATH, BAR),
                ("mHC (mg/s)", "conditions.fuel.flow_mg_s", 1), ("burn time (sec)", "outcome.burn_time_s", 1)],
    "PSI-107": [("Air Rate (cm/s)", "conditions.flow.velocity_cm_s", 1), ("Fuel Rate (mg/s)", "conditions.fuel.flow_mg_s", 1),
                ("Nozzle (mm)", "conditions.fuel.diameter_mm", 1)],
    "PSI-25": [("Calibrated initial O2 % by vol", O2_PATH, 0.01)],
}


def check_against_source(ds):
    """Every checked numeric field must equal its raw source cell x unit factor (0/negative -> null allowed)."""
    import pandas as pd
    frames, n = {}, 0
    for run in ds.runs:
        f = run.source.file
        if f not in frames:
            path = os.path.join(RAW, "run_tables", f)
            for enc in ("utf-8-sig", "cp1252"):
                try:
                    frames[f] = pd.read_csv(path, encoding=enc, dtype=str, skip_blank_lines=False)
                    break
                except UnicodeDecodeError:
                    pass
            frames[f].columns = [re.sub(r"\s+", " ", c).strip() for c in frames[f].columns]
        row = frames[f].iloc[run.source.row - 1]
        flat = pd.json_normalize(dataclasses.asdict(run)).iloc[0]
        for col, path, k in SOURCE_CHECKS.get(run.investigation, []):
            if col not in row.index:
                continue
            raw = pd.to_numeric(row[col], errors="coerce")
            val = flat[path]
            if pd.isna(raw):
                continue  # non-numeric source text: covered by parser unit checks
            if val is None or pd.isna(val):
                assert raw <= 0, (run.id, col, row[col])  # only zero/negative sentinels may become null
                continue
            assert abs(val - raw * k) <= 1e-3 * max(1, abs(raw * k)), (run.id, col, row[col], val)
            n += 1
    return n


def coverage(ds):
    """Markdown coverage report: what each investigation can be used for."""
    df = ds.to_frame()
    cols = {"O₂": O2_PATH, "pressure": P_PATH, "flow": "conditions.flow.velocity_cm_s", "ignited": "outcome.ignited",
            "result": "outcome.result", "burn time": "outcome.burn_time_s", "burning rate K": "outcome.burning_rate_mm2_s",
            "ext. diameter": "outcome.extinction_diameter_mm", "spread rate": "outcome.spread_rate_mm_s"}
    inv = {i.id: i for i in ds.investigations}
    lines = ["# Dataset coverage", "", "Generated by `python3 -m flame.normalize`. Don't edit by hand.", "",
             f"{len(df)} runs, **{int(df.has_outcome.sum())} with an outcome (usable as labels)**. "
             "Percentages are the share of runs with the field filled; (a) = some values assumed, see `run.assumed`.", "",
             "| Investigation | Family | Runs | Has outcome | Censored | " + " | ".join(cols) + " |",
             "|---|---|---|---|---|" + "---|" * len(cols)]
    for acc, g in df.groupby("investigation", sort=False):
        asm = set(p for a in g.assumed for p in a)
        cells = [f"{g[c].notna().mean():.0%}" + (" (a)" if c in asm else "") if g[c].notna().any() else "" for c in cols.values()]
        lines.append(f"| {acc} {inv[acc].acronym} | {inv[acc].category} | {len(g)} | {int(g.has_outcome.sum())} | "
                     f"{int((g['outcome.censored'] == True).sum())} | " + " | ".join(cells) + " |")
    lines += ["", "Never filled by any source table (they exist for the physics engine's predictions): "
              "`temperature_k`, `ignition` (except SAFFIRE), `flame_length_mm`, `flame_temperature_k`.", "",
              "## Not normalized", ""] + [f"- **{i.id} {i.acronym}**: {i.note}" for i in ds.investigations if not i.normalized]
    return "\n".join(lines) + "\n"


def check(ds):
    ids = [r.id for r in ds.runs]
    assert len(ids) == len(set(ids)), "duplicate run ids: " + str({i for i in ids if ids.count(i) > 1})
    per = {}
    for r in ds.runs:
        per[r.investigation] = per.get(r.investigation, 0) + 1
        a, f = r.conditions.atmosphere, r.conditions.fuel
        assert a.o2_frac is None or 0 < a.o2_frac <= 1, (r.id, a.o2_frac)
        assert a.pressure_kpa is None or 20 < a.pressure_kpa < 600, (r.id, a.pressure_kpa)
        assert r.conditions.flow.velocity_cm_s is None or 0 <= r.conditions.flow.velocity_cm_s < 100, (r.id, r.conditions.flow)
        assert r.outcome.censored is None or r.outcome.result is not None, r.id
        assert (r.outcome.ignited is False) == (r.outcome.result == "no_ignition"), r.id
        assert f.thickness_mm is None or 0 < f.thickness_mm < 50, (r.id, f.thickness_mm)
    expect = {"PSI-69": 274, "PSI-39": 79, "PSI-10": 327, "PSI-159": 333, "PSI-107": 469, "PSI-25": 129,
              "PSI-98": 2, "PSI-99": 9, "PSI-100": 2}
    assert per == expect, per
    assert Dataset.from_json(OUT) == ds, "JSON round trip changed data"
    # parser spot checks against hand-read rows
    assert mid("21.5 - 21.7") == 21.6 and mid("22.1 to 22.0") == 22.05 and num("RAMPED") is None
    assert with_unit("037 mm", CM) is None and with_unit("0.27 mm", CM) == 0.27 and with_unit("1 cm", CM) == 10
    b = _bass2_fuel('1/4" black rod')
    assert b.geometry == "rod" and b.diameter_mm == 6.35
    b = _bass2_fuel("100 micron PMMA film   2 cm wide")
    assert (b.name, b.geometry, b.thickness_mm, b.width_mm) == ("pmma", "film", 0.1, 20.0)
    return per


if __name__ == "__main__":
    ds = build()
    per = check(ds)
    n_src = check_against_source(ds)
    open(os.path.join(os.path.dirname(OUT), "coverage.md"), "w").write(coverage(ds))
    print(f"source agreement: {n_src} numeric values re-read from the raw CSVs, all match")
    df = ds.to_frame()
    print(f"wrote {OUT}: {len(ds.runs)} runs from {len(per)} investigations ({len(ds.investigations)} investigations listed)")
    for acc, n in per.items():
        print(f"  {acc:8} {n:4} runs")
    print("non-null share of key columns:")
    for c in ["conditions.atmosphere.o2_frac", "conditions.atmosphere.pressure_kpa", "conditions.flow.velocity_cm_s",
              "outcome.ignited", "outcome.result", "outcome.burn_time_s"]:
        print(f"  {c:38} {df[c].notna().mean():5.0%}")
    print(f"runs linked to media files: {(df['media'].str.len() > 0).mean():.0%}")
