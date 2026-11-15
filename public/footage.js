// Real NASA footage (public/media/, from flame/clips.py): show the nearest real run to some conditions that has a clip.
let media = null;
export async function realFootage(el, { o2, pressure, flow, gravity, phase }, emptyText = "") {
  media ??= await fetch("/media/index.json").then(r => (r.ok ? r.json() : { runs: {} })).catch(() => ({ runs: {} }));
  const q = new URLSearchParams({ o2, pressure, flow, gravity, k: 50, ...(phase ? { phase } : {}) });
  const near = await fetch(`/api/nearest?${q}`).then(r => r.json()).catch(() => null);
  const m = near?.matches.find(x => media.runs[x.run_id]);
  const capEl = document.getElementById(el.dataset.cap || "");
  if (!m && capEl) capEl.textContent = "Real NASA footage";
  if (!m) { el.innerHTML = emptyText ? `<p class="mute" style="margin:0">${emptyText}</p>` : ""; el.hidden = !emptyText; return null; }
  const NAMES = { pmma: "acrylic (PMMA)", sibal: "cotton/fiberglass fabric", nomex: "Nomex fabric", silicone: "silicone", "n-dodecane": "dodecane" };
  const fl = m.flow_cm_s == null ? "?" : m.flow_cm_s >= 1 ? Math.round(m.flow_cm_s) : m.flow_cm_s.toFixed(1);
  const c = media.runs[m.run_id], esc = s => String(s ?? "").replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
  el.hidden = false;
  if (capEl) capEl.innerHTML = `Real NASA run ${esc(m.run_id)} (${esc(m.acronym)}): ${esc(NAMES[m.fuel] || m.fuel)}, ${m.o2_pct} % O₂, ${fl} cm/s` +
    (m.match === "near" ? "" : ` · <span style="color:#f6c945">closest available</span>`);
  el.innerHTML = `<video src="/${esc(c.clip)}" poster="/${esc(c.thumbnail)}" muted autoplay loop playsinline></video>
    <div class="vl"><b>Real NASA footage, brightened for visibility</b> · run ${esc(m.run_id)} (${esc(m.acronym)}) · ${esc(NAMES[m.fuel] || m.fuel)} · ${m.o2_pct} % O₂ · ${fl} cm/s
    ${m.match === "near" ? "" : `<br><span style="color:#f6c945">Closest available. Your setting differs: ${esc((m.differences[0] || "different conditions").replace("than this run", "than in this run"))}</span>`}</div>`;
  return m;
}
