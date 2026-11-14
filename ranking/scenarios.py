"""Habitat scenarios the ranking scores investigations against.

Units follow flame/schema.py: O2 as a mole fraction (0.21 = air), pressure in kPa, flow in cm/s.
"""
from dataclasses import asdict, dataclass

ATM_KPA = 101.325
PSI_KPA = 6.89476


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    o2_frac: float           # target O2 mole fraction
    pressure_kpa: float      # target total pressure
    gravity_g: float         # 0 = microgravity, 0.166 = Moon, 0.38 = Mars
    flow_cm_s: float         # typical ventilation speed past a burning item
    note: str = ""
    # How far away a run can be and still count as "close" (1 sigma)
    o2_tol: float = 0.04     # +-4 percentage points of O2
    p_tol_log: float = 0.20  # +-~20 % in pressure (log ratio)
    flow_tol: float = 15.0   # +-15 cm/s

    def to_dict(self):
        d = asdict(self)
        d["o2_pct"] = round(self.o2_frac * 100, 1)
        d["pressure_psi"] = round(self.pressure_kpa / PSI_KPA, 1)
        return d


SCENARIOS = {
    s.id: s for s in [
        Scenario("iss", "ISS / spacecraft cabin", 0.21, ATM_KPA, 0.0, 10.0,
                 "Sea-level air, microgravity, ventilation ~5-20 cm/s."),
        Scenario("moon_base", "Moon Base", 0.30, 10.2 * PSI_KPA, 0.166, 10.0,
                 "Planned >=30% O2 at <=10.2 psi. PSI has no partial-gravity data yet; "
                 "microgravity and 1 g results bound the lunar case."),
        Scenario("pressurized_rover", "Pressurized rover", 0.30, 10.2 * PSI_KPA, 0.166, 20.0,
                 "Same atmosphere as the Moon Base, smaller cabin with stronger local airflow (assumption)."),
        Scenario("mars_base", "Mars base", 0.30, 10.2 * PSI_KPA, 0.38, 10.0,
                 "Atmosphere assumed equal to the Moon Base (no official figure in the challenge)."),
    ]
}


def custom(o2_frac, pressure_kpa, gravity_g=0.0, flow_cm_s=10.0, name="Custom"):
    """Build a scenario from sliders (e.g. the physics-engine UI)."""
    return Scenario("custom", name, o2_frac, pressure_kpa, gravity_g, flow_cm_s)
