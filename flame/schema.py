"""Shared data contract between the data pipeline and the physics engine.

One JSON file (see examples/runs.sample.json):
    {"schema_version": "0.1", "investigations": [Investigation...], "runs": [Run...]}

Rules
- Units are in the field name (_kpa, _cm_s, _mm, _s, _w, _k). Gas amounts are mole fractions (0.21 = air).
- Unknown/not measured = null. Never guess a value to fill a gap.
- Physics engine contract: predict(run.conditions) -> Outcome, compare with run.outcome.
- Anything source-specific that doesn't fit goes in `extra`; the original row is traceable via `source`.
- Values filled by assumption (not measured) are listed by field path in `run.assumed`.
"""
from __future__ import annotations

import dataclasses as dc
import json
import typing
from dataclasses import dataclass, field
from typing import Literal, Optional

SCHEMA_VERSION = "0.2"

Phase = Literal["solid", "liquid", "gas"]
Geometry = Literal["film", "rod", "fabric", "sheet", "droplet", "spherical_burner", "jet", "flat_burner", "other"]
FlowDirection = Literal["concurrent", "opposed", "coflow", "quiescent", "other"]
Result = Literal["burnout", "extinction", "disruption", "no_ignition", "terminated", "other"]
O2Location = Literal["ambient", "burner_stream"]


@dataclass
class Fuel:
    name: str                                  # normalized lowercase: "pmma", "methanol", "ethane", "sibal"
    phase: Phase
    geometry: Optional[Geometry] = None
    thickness_mm: Optional[float] = None       # solids
    width_mm: Optional[float] = None
    length_mm: Optional[float] = None
    diameter_mm: Optional[float] = None        # droplet initial diameter, rod or burner diameter
    flow_mg_s: Optional[float] = None          # gaseous fuel mass flow
    fuel_frac: Optional[float] = None          # fuel mole fraction in the feed gas (rest is diluent)


@dataclass
class Atmosphere:
    o2_frac: Optional[float] = None
    n2_frac: Optional[float] = None
    he_frac: Optional[float] = None
    co2_frac: Optional[float] = None
    pressure_kpa: Optional[float] = None       # 101.325 = sea level, ~70.3 = 10.2 psi lunar habitat
    temperature_k: Optional[float] = None


@dataclass
class Flow:
    velocity_cm_s: Optional[float] = None      # imposed flow past the fuel; 0 = quiescent
    direction: Optional[FlowDirection] = None


@dataclass
class Ignition:
    power_w: Optional[float] = None
    duration_s: Optional[float] = None


@dataclass
class Conditions:
    """Inputs to an experiment, and inputs to the physics engine."""
    fuel: Fuel
    atmosphere: Atmosphere = field(default_factory=Atmosphere)
    flow: Flow = field(default_factory=Flow)
    ignition: Ignition = field(default_factory=Ignition)
    gravity_g: float = 0.0                     # 0 = microgravity (ISS/Cygnus), 1 = ground, 0.166 = Moon
    o2_location: O2Location = "ambient"        # "burner_stream" for inverse flames: atmosphere.o2_frac is the
                                               # O2 fraction flowing OUT of the burner, the ambient is fuel


@dataclass
class Outcome:
    """What was observed, and what the physics engine predicts."""
    ignited: Optional[bool] = None
    result: Optional[Result] = None            # how the burn ended
    censored: Optional[bool] = None            # True: burn_time_s is a lower bound (operator stopped it, droplet
                                               # disrupted), not a natural extinction/burnout time
    burn_time_s: Optional[float] = None
    spread_rate_mm_s: Optional[float] = None   # solid flame spread
    burning_rate_mm2_s: Optional[float] = None # droplet d^2-law burning-rate constant K
    extinction_diameter_mm: Optional[float] = None
    flame_length_mm: Optional[float] = None
    flame_temperature_k: Optional[float] = None


@dataclass
class Source:
    file: str                                  # PSI file name the row came from
    row: int                                   # 1-based data row in that file


@dataclass
class Run:
    id: str                                    # "<investigation>/<test id>", e.g. "PSI-69/20CAL08"
    investigation: str                         # "PSI-69"
    conditions: Conditions
    outcome: Outcome = field(default_factory=Outcome)
    date: Optional[str] = None                 # ISO 8601 "2009-03-05"
    has_outcome: bool = False                  # any outcome field observed -> usable as a training label
    assumed: list[str] = field(default_factory=list)  # field paths filled by assumption, e.g. cabin pressure
    media: list[str] = field(default_factory=list)   # PSI file names of videos/images for this run
    source: Optional[Source] = None
    extra: dict = field(default_factory=dict)


@dataclass
class Investigation:
    id: str                                    # "PSI-69"
    acronym: str                               # "FLEX"
    title: str
    category: Literal["solid", "droplet", "gaseous", "smoke", "other"]
    hardware: Optional[str] = None             # "Microgravity Science Glovebox (MSG)", ...
    platform: Optional[str] = None             # "International Space Station (ISS)", "Cygnus Spacecraft"
    doi: Optional[str] = None
    objective: Optional[str] = None
    normalized: bool = False                   # True if its run table is in `runs`
    note: Optional[str] = None                 # why it is / isn't normalized
    publications: list[dict] = field(default_factory=list)   # [{"title": ..., "doi": ...}]


@dataclass
class Dataset:
    investigations: list[Investigation] = field(default_factory=list)
    runs: list[Run] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_json(self, path):
        with open(path, "w") as f:
            json.dump(dc.asdict(self), f, indent=2)

    def to_frame(self):
        """Flat pandas DataFrame, one row per run, dotted column names (conditions.atmosphere.o2_frac, ...)."""
        import pandas as pd
        return pd.json_normalize([dc.asdict(r) for r in self.runs])

    @classmethod
    def from_json(cls, path) -> "Dataset":
        d = json.load(open(path))
        if d.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"schema_version {d.get('schema_version')!r} != {SCHEMA_VERSION!r}")
        return _build(cls, d)


def _build(cls, d):
    """dict -> dataclass, recursively. Unknown keys raise, so typos fail loudly."""
    hints = typing.get_type_hints(cls)
    names = {f.name for f in dc.fields(cls)}
    if unknown := set(d) - names:
        raise ValueError(f"{cls.__name__}: unknown keys {sorted(unknown)}")
    kw = {}
    for k, v in d.items():
        t = hints[k]
        t = next((a for a in typing.get_args(t) if a is not type(None)), t) if typing.get_origin(t) is typing.Union else t
        if dc.is_dataclass(t) and isinstance(v, dict):
            v = _build(t, v)
        elif typing.get_origin(t) is list and typing.get_args(t) and dc.is_dataclass(typing.get_args(t)[0]):
            v = [_build(typing.get_args(t)[0], x) for x in v]
        kw[k] = v
    return cls(**kw)


if __name__ == "__main__":
    import os, tempfile
    ex = os.path.join(os.path.dirname(__file__), "..", "examples", "runs.sample.json")
    ds = Dataset.from_json(ex)
    assert ds.runs and all(r.investigation in {i.id for i in ds.investigations} for r in ds.runs)
    assert isinstance(ds.runs[0].conditions.atmosphere, Atmosphere)
    tmp = os.path.join(tempfile.mkdtemp(), "rt.json")
    ds.to_json(tmp)
    assert Dataset.from_json(tmp) == ds, "round trip changed data"
    try:
        _build(Flow, {"velocity_cm_s": 1, "speed": 2})
        raise AssertionError("unknown key accepted")
    except ValueError:
        pass
    print(f"ok: {len(ds.investigations)} investigations, {len(ds.runs)} runs")
