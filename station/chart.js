// Coverage chart: O2 vs pressure, one dot per test run, coloured by investigation.
// Needs the Plotly global (loaded in index.html).

const PALETTE = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#be185d", "#4d7c0f", "#475569"];

export function drawChart(div, tested, investigations, habitats) {
  if (!window.Plotly) {
    div.textContent = "The chart library could not be loaded (check your internet connection).";
    return;
  }
  const byInv = new Map();
  for (const r of tested) {
    const a = r.conditions.atmosphere;
    if (a.o2_frac == null || a.pressure_kpa == null) continue;   // unknown is not zero: skip, don't plot at 0
    if (!byInv.has(r.investigation)) byInv.set(r.investigation, []);
    byInv.get(r.investigation).push(r);
  }

  const traces = [...byInv.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([id, runs], i) => {
    const inv = investigations[id];
    return {
      type: "scatter", mode: "markers",
      name: `${id} ${inv?.acronym ?? ""}`.trim(),
      x: runs.map(r => r.conditions.atmosphere.o2_frac * 100),
      y: runs.map(r => r.conditions.atmosphere.pressure_kpa),
      // hollow = pressure was assumed (cabin air), not measured
      marker: {
        size: 8, color: PALETTE[i % PALETTE.length], opacity: 0.7,
        symbol: runs.map(r => (r.assumed.includes("conditions.atmosphere.pressure_kpa") ? "circle-open" : "circle")),
        line: { width: 1.5, color: PALETTE[i % PALETTE.length] },
      },
      text: runs.map(r => `${r.id}<br>${r.conditions.fuel.name}${r.has_outcome ? "" : " (no outcome recorded)"}`),
      hovertemplate: "%{text}<br>O₂ %{x:.1f} %<br>%{y:.1f} kPa<extra></extra>",
    };
  });

  traces.push(habitatTrace(habitats));
  const layout = {
    height: 540,
    margin: { l: 70, r: 20, t: 20, b: 60 },
    xaxis: { title: "Oxygen (% of atmosphere)", range: [0, 100], zeroline: false },
    yaxis: { title: "Pressure (kPa)  ·  101.3 kPa = 1 atm", range: [0, 330], zeroline: false },
    hovermode: "closest",
    legend: { orientation: "h", y: -0.2 },
    shapes: [{ type: "line", x0: 0, x1: 100, y0: 101.325, y1: 101.325, line: { color: "#888", dash: "dot", width: 1 } }],
  };
  Plotly.newPlot(div, traces, layout, { responsive: true, displaylogo: false });
  div._habitatTraceIndex = traces.length - 1;
}

function habitatTrace(habitats) {
  return {
    type: "scatter", mode: "markers+text",
    name: "Habitats (current slider values)",
    x: habitats.map(h => h.o2_frac * 100),
    y: habitats.map(h => h.pressure_kpa),
    text: habitats.map(h => h.name),
    textposition: "top center",
    marker: { symbol: "star", size: 20, color: "#facc15", line: { width: 2, color: "#111" } },
    hovertemplate: "%{text}<br>O₂ %{x:.1f} %<br>%{y:.1f} kPa<extra></extra>",
  };
}

// Called whenever a slider moves: only the habitat markers change.
export function moveHabitats(div, habitats) {
  if (!window.Plotly || div._habitatTraceIndex == null) return;
  Plotly.restyle(div, {
    x: [habitats.map(h => h.o2_frac * 100)],
    y: [habitats.map(h => h.pressure_kpa)],
  }, [div._habitatTraceIndex]);
}
