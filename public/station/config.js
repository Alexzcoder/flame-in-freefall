// Habitat settings. This is configuration, NOT data.
// Units follow flame/schema.py: mole fractions, kPa, cm/s. 1 atm = 14.7 psi = 101.325 kPa.
// Airflow values are placeholders, not verified.

export const HABITATS = [
  {
    id: "iss",
    name: "ISS module",
    gravity_g: 0.0,
    o2_frac: 0.21,
    pressure_kpa: 101.325,
    airflow_cm_s: 10,
    airflow_verified: false,
    materials: ["pmma", "sibal"],   // the only solids with usable outcomes (pmma 18, sibal 3); "cotton" = sibal
  },
  {
    id: "moon",
    name: "Moon base",
    gravity_g: 0.166,
    o2_frac: 0.30,
    pressure_kpa: 70.3, // 10.2 psi
    airflow_cm_s: 5,
    airflow_verified: false,
    materials: ["pmma", "sibal"],
  },
  {
    id: "mars",
    name: "Mars base",
    gravity_g: 0.38,
    o2_frac: 0.30,       // no official figure: assumed equal to the Moon base (same as ranking/scenarios.py)
    pressure_kpa: 70.3,
    airflow_cm_s: 5,
    airflow_verified: false,
    materials: ["pmma", "sibal"],
  },
];
