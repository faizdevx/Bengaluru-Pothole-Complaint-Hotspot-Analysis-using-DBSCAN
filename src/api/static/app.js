"use strict";
/* Shared helpers + page renderers. All text is inserted via textContent / esc(). */
const $ = (s, r = document) => r.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 0) => (n === null || n === undefined || n === "Insufficient data" ? (n ?? "—") : Number(n).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }));
const pct = (x, d = 1) => (x === null || x === undefined || typeof x === "string" ? (x ?? "—") : (100 * x).toFixed(d) + "%");
const day = (iso) => (iso ? String(iso).slice(0, 10) : "—");
const NOT_RUN = "No analysis has been run yet.";

async function getJSON(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(body.error || r.statusText); e.status = r.status; throw e; }
  return body;
}
function setState(msg, kind = "") {
  const el = $("#state"); if (!el) return;
  el.hidden = false; el.className = "state " + kind; el.textContent = "";
  if (kind === "") { const s = document.createElement("span"); s.className = "spinner"; el.appendChild(s); }
  el.appendChild(document.createTextNode(msg));
}
const hideState = () => { const el = $("#state"); if (el) el.hidden = true; };
function fail(e) {
  if (e.status === 404 && e.message === NOT_RUN) setState(NOT_RUN + " Run: python scripts/run_pipeline.py", "empty");
  else setState("Could not load data: " + e.message, "error");
}
function kpi(label, value, sub = "") {
  return `<div class="kpi"><div class="l">${esc(label)}</div><div class="n${String(value).length > 9 ? " sm" : ""}">${esc(value)}</div><div class="s">${esc(sub)}</div></div>`;
}
const trendTag = (t) => `<span class="tag ${t === "Increasing" ? "inc" : t === "Decreasing" ? "dec" : ""}">${esc(t)}</span>`;
const recentTxt = (h) => typeof h.recent_3_month_count === "string" ? h.recent_3_month_count :
  `${h.recent_3_month_count} (3 mo) vs ${h.historical_average}/mo` + (typeof h.recent_vs_historical_change === "number" ? ` · ${(h.recent_vs_historical_change * 100).toFixed(0)}%` : "");

/* ---------- SVG charts ---------- */
function barChart(el, rows, { x, y, label = (r) => r[x], color = "var(--bar)", ytitle = "", fmtY = (v) => fmt(v), horizontal = false }) {
  if (!rows.length) { el.innerHTML = '<p class="state empty">No data.</p>'; return; }
  const W = 720, H = horizontal ? 24 * rows.length + 30 : 260, m = horizontal ? { l: 190, r: 40, t: 8, b: 20 } : { l: 44, r: 8, t: ytitle ? 24 : 10, b: 44 };
  const max = Math.max(...rows.map((r) => r[y] || 0), 1e-9);
  let g = "";
  if (horizontal) {
    const bh = (H - m.t - m.b) / rows.length;
    rows.forEach((r, i) => {
      const w = ((r[y] || 0) / max) * (W - m.l - m.r), yy = m.t + i * bh;
      g += `<text x="${m.l - 6}" y="${yy + bh / 2 + 4}" text-anchor="end">${esc(label(r))}</text><rect x="${m.l}" y="${yy + 2}" width="${w}" height="${bh - 4}" fill="${color}"><title>${esc(label(r))}: ${esc(fmtY(r[y]))}</title></rect><text x="${m.l + w + 4}" y="${yy + bh / 2 + 4}">${esc(fmtY(r[y]))}</text>`;
    });
  } else {
    const bw = (W - m.l - m.r) / rows.length;
    for (let t = 0; t <= 4; t++) { const v = (max * t) / 4, yy = H - m.b - (v / max) * (H - m.t - m.b); g += `<line x1="${m.l}" x2="${W - m.r}" y1="${yy}" y2="${yy}" stroke="var(--line)"/><text x="${m.l - 4}" y="${yy + 4}" text-anchor="end">${esc(fmtY(v))}</text>`; }
    rows.forEach((r, i) => {
      const h = ((r[y] || 0) / max) * (H - m.t - m.b), xx = m.l + i * bw;
      g += `<rect x="${xx + 0.5}" y="${H - m.b - h}" width="${Math.max(bw - 1, 1)}" height="${h}" fill="${color}"><title>${esc(label(r))}: ${esc(fmtY(r[y]))}</title></rect>`;
      if (i % Math.ceil(rows.length / 12) === 0) g += `<text transform="translate(${xx + bw / 2},${H - m.b + 12}) rotate(45)" text-anchor="start">${esc(r[x])}</text>`;
    });
    if (ytitle) g += `<text x="4" y="12">${esc(ytitle)}</text>`;
  }
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Bar chart">${g}</svg>`;
}
function lineChart(el, rows, { x, y, color = "var(--bar2)", fmtY = (v) => (v * 100).toFixed(0) + "%" }) {
  const pts = rows.filter((r) => r[y] !== null && r[y] !== undefined);
  if (pts.length < 2) { el.innerHTML = '<p class="state empty">Not enough data.</p>'; return; }
  const W = 720, H = 240, m = { l: 44, r: 8, t: 10, b: 44 }, max = Math.max(...pts.map((r) => r[y]), 1e-9), n = rows.length;
  const X = (i) => m.l + (i / (n - 1)) * (W - m.l - m.r), Y = (v) => H - m.b - (v / max) * (H - m.t - m.b);
  let g = "";
  for (let t = 0; t <= 4; t++) { const v = (max * t) / 4; g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${m.l - 4}" y="${Y(v) + 4}" text-anchor="end">${esc(fmtY(v))}</text>`; }
  const d = rows.map((r, i) => (r[y] === null || r[y] === undefined ? null : `${X(i)},${Y(r[y])}`)).filter(Boolean).join(" ");
  g += `<polyline points="${d}" fill="none" stroke="${color}" stroke-width="2"/>`;
  rows.forEach((r, i) => { if (r[y] != null) g += `<circle cx="${X(i)}" cy="${Y(r[y])}" r="2.5" fill="${color}"><title>${esc(r[x])}: ${esc(fmtY(r[y]))}</title></circle>`; if (i % Math.ceil(n / 12) === 0) g += `<text transform="translate(${X(i)},${H - m.b + 12}) rotate(45)">${esc(r[x])}</text>`; });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Line chart">${g}</svg>`;
}

/* ---------- sortable table ---------- */
function sortableTable(table, cols, rows, { onRow } = {}) {
  const thead = $("thead tr", table), tbody = $("tbody", table);
  let sort = { key: cols[0].key, dir: 1 };
  const cmp = (a, b) => { const x = a[sort.key], y = b[sort.key]; const xs = typeof x === "string" || x == null, ys = typeof y === "string" || y == null; if (xs && ys) return String(x ?? "").localeCompare(String(y ?? "")) * sort.dir; if (xs) return 1; if (ys) return -1; return (x - y) * sort.dir; };
  thead.innerHTML = "";
  cols.forEach((c) => { const th = document.createElement("th"); if (c.left) th.className = "l"; th.scope = "col"; const b = document.createElement("button"); b.textContent = c.label; b.addEventListener("click", () => { sort = { key: c.key, dir: sort.key === c.key ? -sort.dir : (c.defaultDesc ? -1 : 1) }; draw(); }); th.appendChild(b); thead.appendChild(th); });
  function draw() {
    thead.querySelectorAll("th").forEach((th, i) => th.setAttribute("aria-sort", cols[i].key === sort.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"));
    tbody.innerHTML = "";
    [...rows].sort(cmp).forEach((r) => { const tr = document.createElement("tr"); cols.forEach((c) => { const td = document.createElement("td"); if (c.left) td.className = "l"; if (c.html) td.innerHTML = c.html(r); else td.textContent = c.fmt ? c.fmt(r[c.key], r) : (r[c.key] ?? "—"); tr.appendChild(td); }); if (onRow) { tr.style.cursor = "pointer"; tr.addEventListener("click", () => onRow(r)); } tbody.appendChild(tr); });
  }
  draw(); return { setRows(r) { rows = r; draw(); } };
}

/* ---------- provenance strip (every page) ---------- */
async function provenance() {
  try {
    const d = await getJSON("/api/data-status");
    $("#prov-retrieved").textContent = d.last_source_retrieval ? new Date(d.last_source_retrieval).toUTCString().replace("GMT", "UTC") : "not retrieved yet";
    if (d.date_min) $("#prov-range").textContent = `(records ${day(d.date_min)} to ${day(d.date_max)})`;
  } catch (e) { $("#prov-retrieved").textContent = "unavailable"; }
}

/* ---------- pages ---------- */
const pages = {
  async dashboard() {
    setState("Loading summary…");
    const [s, tl] = await Promise.all([getJSON("/api/summary"), getJSON("/api/timeline")]);
    hideState(); $("#dash").hidden = false;
    $("#kpis").innerHTML = [
      kpi("Pothole complaints", fmt(s.total_pothole_reports), "taxonomy-filtered"),
      kpi("Valid coordinates", fmt(s.valid_coordinate_pothole_reports), `${fmt(s.analysed_pothole_reports)} analysed inside boundary`),
      kpi("DBSCAN clusters", fmt(s.clusters), `eps ${s.eps_meters} m · min_samples ${s.min_samples}`),
      kpi("Noise", s.noise_percentage.toFixed(1) + "%", `${fmt(s.noise_reports)} isolated reports`),
      kpi("Persistent complaint areas", fmt(s.persistent_complaint_areas), `of ${s.wards_total} wards (fixed units)`),
      kpi("Highest-activity cluster", s.highest_activity_cluster ? "#" + s.highest_activity_cluster.cluster_id : "—", s.highest_activity_cluster ? `${s.highest_activity_cluster.reports} reports` : ""),
      kpi("Source date range", `${day(s.source_date_range.min)}`, `to ${day(s.source_date_range.max)}`),
      kpi("Last source retrieval", day(s.last_source_retrieval), "historical file, not live"),
    ].join("");
    barChart($("#chart-city"), tl.series, { x: "month", y: "pothole_reports", ytitle: "reports / month" });
    const t = tl.trend.pothole_count, r = tl.recent;
    $("#city-note").textContent = `Observed trend: ${t.trend} (Kendall τ ${t.tau}). Latest 3 months: ${typeof r.recent_3_month_count === "number" ? (r.recent_3_month_count / 3).toFixed(1) : "n/a"}/month vs ${r.historical_average}/month earlier.`;
    const h = s.highest_activity_cluster;
    $("#top-cluster").innerHTML = h ? `<dl class="facts"><dt>Cluster</dt><dd><a href="/clusters?id=${h.cluster_id}">#${h.cluster_id}</a></dd><dt>Reports</dt><dd>${h.reports}</dd><dt>Approx. radius</dt><dd>${fmt(h.radius_m)} m</dd></dl>` : "<p class='state empty'>No clusters.</p>";
  },

  async hotspots() {
    setState("Loading hotspots…");
    const d = await getJSON("/api/hotspots"); hideState(); $("#hs").hidden = false;
    const cr = d.city_recent;
    $("#city-baseline").textContent = typeof cr.recent_3_month_count === "number" ? `City-wide baseline: ${(cr.recent_3_month_count / 3).toFixed(1)} reports/month in the latest 3 months vs ${cr.historical_average}/month earlier (${(cr.recent_vs_historical_change * 100).toFixed(0)}%). Cluster declines should be compared with this.` : "City-wide baseline unavailable.";
    const cols = [
      { key: "rank", label: "Rank" }, { key: "cluster_id", label: "Cluster ID", html: (r) => `<a href="/clusters?id=${r.cluster_id}">#${r.cluster_id}</a>` },
      { key: "reports", label: "Reports", defaultDesc: true }, { key: "radius_m", label: "Radius (m)", fmt: (v) => fmt(v) },
      { key: "persistence", label: "Persistence", fmt: (v, r) => v == null ? "—" : `${r.active_months}/${r.eligible_months} (${pct(v, 0)})` },
      { key: "recent_3_month_count", label: "Recent activity", fmt: (v, r) => recentTxt(r) },
      { key: "observed_trend", label: "Observed trend", html: (r) => trendTag(r.observed_trend) },
      { key: "complaint_share", label: "Complaint share", fmt: (v) => pct(v, 0) },
    ];
    const tb = sortableTable($("#tbl"), cols, d.hotspots);
    const apply = async () => { const q = new URLSearchParams(); const m = $("#f-min").value, t = $("#f-trend").value; if (m) q.set("min_reports", m); if (t) q.set("trend", t); const r = await getJSON("/api/hotspots?" + q); tb.setRows(r.hotspots); $("#count").textContent = `${r.count} clusters`; };
    $("#f-min").addEventListener("change", apply); $("#f-trend").addEventListener("change", apply);
    $("#count").textContent = `${d.count} clusters`;
  },

  async timeline() {
    setState("Loading timeline…");
    const [city, w, h] = await Promise.all([getJSON("/api/timeline"), getJSON("/api/spatial-units"), getJSON("/api/hotspots")]);
    hideState(); $("#tl").hidden = false;
    const draw = (series, title, trend) => {
      $("#tl-title").textContent = title;
      barChart($("#chart-a"), series, { x: "month", y: "pothole_reports", ytitle: "reports / month" });
      lineChart($("#chart-b"), series, { x: "month", y: "pothole_share" });
      $("#tl-trend").textContent = trend || "";
    };
    const cityTrend = () => { const t = city.trend.pothole_count; draw(city.series, "Monthly pothole complaints, city-wide", `Observed trend: ${t.trend} (Kendall τ ${t.tau}, BH-adjusted q ${t.q_value.toExponential(1)}). Observed trend, not a verified change in road condition.`); };
    cityTrend();
    $("#unit-type").addEventListener("change", async (e) => {
      const v = e.target.value; $("#unit-wrap").hidden = v === "city";
      if (v === "city") return cityTrend();
      const sel = $("#unit-id"); sel.innerHTML = "";
      (v === "ward" ? [...w.units].sort((a, b) => b.total_reports - a.total_reports).map((u) => [u.unit_id, `${u.ward_name} (${u.total_reports})`]) : h.hotspots.map((x) => [x.cluster_id, `Cluster #${x.cluster_id} (${x.reports})`])).forEach(([id, t]) => { const o = document.createElement("option"); o.value = id; o.textContent = t; sel.appendChild(o); });
      sel.dispatchEvent(new Event("change"));
    });
    $("#unit-id").addEventListener("change", async (e) => {
      const v = $("#unit-type").value; const d = await getJSON(`/api/timeline?unit_type=${v}&unit_id=${e.target.value}`);
      const u = v === "ward" ? w.units.find((x) => x.unit_id == e.target.value) : h.hotspots.find((x) => x.cluster_id == e.target.value);
      draw(d.series, e.target.selectedOptions[0].textContent, `Observed trend: ${v === "ward" ? u.trend : u.observed_trend}. Small counts: interpret with caution.`);
    });
  },

  async clusters() {
    setState("Loading clusters…");
    const d = await getJSON("/api/hotspots?limit=500"); hideState(); $("#ex").hidden = false;
    const ul = $("#cl-list"); const want = new URLSearchParams(location.search).get("id");
    d.hotspots.forEach((h) => { const li = document.createElement("li"), b = document.createElement("button"); b.textContent = `#${h.rank} · Cluster ${h.cluster_id} · ${h.reports} reports`; b.addEventListener("click", () => show(h.cluster_id, b)); li.appendChild(b); ul.appendChild(li); if (String(h.cluster_id) === want) setTimeout(() => show(h.cluster_id, b)); });
    async function show(id, btn) {
      ul.querySelectorAll("button").forEach((x) => x.removeAttribute("aria-current")); btn.setAttribute("aria-current", "true");
      const c = await getJSON("/api/hotspots/" + id), el = $("#cl-detail");
      el.innerHTML = `<h2>Cluster #${esc(c.cluster_id)} <span class="muted">(rank ${esc(c.rank)})</span></h2>
      <dl class="facts"><dt>Reports</dt><dd>${c.reports}</dd><dt>Approx. radius</dt><dd>${fmt(c.radius_m)} m</dd>
      <dt>First report</dt><dd>${day(c.date_min)}</dd><dt>Latest report</dt><dd>${day(c.date_max)}</dd>
      <dt>Spatial density</dt><dd>${fmt(c.density_per_km2, 1)} reports/km²</dd>
      <dt>Persistence</dt><dd>${c.persistence == null ? "Unavailable" : `${c.active_months}/${c.eligible_months} months active (${pct(c.persistence, 0)})`}</dd>
      <dt>Recent activity</dt><dd>${esc(recentTxt(c))}</dd><dt>Observed trend</dt><dd>${trendTag(c.observed_trend)}</dd>
      <dt>Complaint share</dt><dd>${pct(c.complaint_share, 0)} of ${c.all_complaints_in_footprint} complaints in the footprint</dd>
      <dt>Distinct coordinates</dt><dd>${c.distinct_coordinates}${c.single_coordinate_cluster ? " (single repeated location)" : ""}</dd></dl>
      <h2 style="margin-top:14px">Monthly reports</h2><div id="cl-chart" class="chart"></div>
      <p class="muted">The cluster boundary is a visualization boundary (50 m-buffered convex hull), not a pothole area. Activity ≠ severity.</p>`;
      barChart($("#cl-chart"), c.monthly, { x: "month", y: "pothole_reports" });
    }
  },

  async spatial() {
    setState("Loading wards…");
    const d = await getJSON("/api/spatial-units"); hideState(); $("#sp").hidden = false;
    const p = d.persistence, u = d.units;
    $("#sp-def").textContent = `Unit: ${d.unit}. Active month = ≥ T reports where T comes from a Poisson null at the city-wide rate (per-ward T shown below); persistent = active in more months than a Binomial null allows (p ≤ 0.01). ${p.persistent_wards} of ${u.length} wards qualify. ${p.caveat}`;
    barChart($("#bar-count"), [...u].sort((a, b) => b.total_reports - a.total_reports).slice(0, 15), { x: "ward_name", y: "total_reports", horizontal: true });
    barChart($("#bar-share"), u.filter((x) => x.all_complaints >= 50).sort((a, b) => b.pothole_share - a.pothole_share).slice(0, 15), { x: "ward_name", y: "pothole_share", horizontal: true, fmtY: (v) => (v * 100).toFixed(0) + "%", color: "var(--bar2)" });
    const cols = [
      { key: "ward_name", label: "Ward", left: true }, { key: "zone", label: "Zone", left: true },
      { key: "total_reports", label: "Pothole reports", defaultDesc: true }, { key: "all_complaints", label: "All complaints" },
      { key: "pothole_share", label: "Pothole share", fmt: (v) => pct(v, 0) }, { key: "area_km2", label: "Area km²", fmt: (v) => fmt(v, 1) },
      { key: "active_month_threshold", label: "Active-month T" }, { key: "persistence", label: "Persistence", fmt: (v, r) => v == null ? "—" : `${r.active_months}/${r.eligible_months}` },
      { key: "persistent", label: "Persistent", fmt: (v) => v ? "Yes" : "No" }, { key: "trend", label: "Observed trend", html: (r) => trendTag(r.trend) },
    ];
    const t = sortableTable($("#w-tbl"), cols, u);
    const f = () => { const q = $("#w-q").value.toLowerCase(), pe = $("#w-pers").checked; t.setRows(u.filter((x) => x.ward_name.toLowerCase().includes(q) && (!pe || x.persistent))); };
    $("#w-q").addEventListener("input", f); $("#w-pers").addEventListener("change", f);
  },

  async parameters() {
    setState("Loading parameters…");
    const d = await getJSON("/api/parameters"); hideState(); $("#pm").hidden = false;
    $("#pm-kpis").innerHTML = [kpi("Distance metric", "Haversine", d.distance_metric.replace("haversine ", "")), kpi("eps", d.eps_meters + " m", "exposed in metres"), kpi("min_samples", d.min_samples, "counts the point itself"), kpi("Dataset size", fmt(d.dataset_size), "pothole reports clustered")].join("");
    const s = d.params.selection_criteria, sel = d.params.selected_row;
    $("#pm-why").innerHTML = `<p>No setting is claimed to be optimal. ${d.sweep.length} settings were swept; the selection required: no sanity warnings, noise ≤ ${s.max_noise_percentage}%, max cluster radius ≤ ${s.max_cluster_radius_m} m, neighbour stability ARI ≥ ${s.min_stability_ari}, ≥ ${s.min_cluster_count} clusters, and ≥ ${s.min_observed_to_baseline_cluster_ratio}× the cluster count of a baseline made from random same-size subsets of non-pothole complaints. Silhouette is not used.</p>
      <p>Selected: eps ${sel.eps_meters} m / min_samples ${sel.min_samples}: ${sel.cluster_count} clusters, ${sel.noise_percentage}% noise; baseline ${sel.baseline_cluster_count_mean} ± ${sel.baseline_cluster_count_sd} clusters, ${sel.baseline_noise_percentage_mean}% noise.</p>
      <p>Sensitivity including suspected fallback pins: ${d.params.sensitivity_with_fallback_pins.cluster_count} clusters, ${d.params.sensitivity_with_fallback_pins.noise_percentage}% noise. HDBSCAN (secondary): ${d.params.hdbscan_secondary.clusters} clusters, ARI vs DBSCAN ${d.params.hdbscan_secondary.ari_vs_selected_dbscan}.</p>`;
    const cols = ["eps_meters", "min_samples", "cluster_count", "noise_percentage", "largest_cluster_size", "largest_cluster_share", "median_cluster_size", "stability_ari", "cluster_ratio_vs_baseline", "silhouette_supplementary"].map((k) => ({ key: k, label: k.replace(/_/g, " ") }));
    cols.push({ key: "selected", label: "status", fmt: (v, r) => v ? "SELECTED" : r.passes_selection_criteria ? "passes" : r.warnings ? "warning" : "" });
    sortableTable($("#sw"), cols, d.sweep);
    const ws = $("#pm-warn"); (d.warnings.length ? d.warnings : ["No warnings."]).forEach((w) => { const li = document.createElement("li"); li.textContent = w; ws.appendChild(li); });
  },

  async quality() {
    setState("Loading data quality…");
    const [q, st] = await Promise.all([getJSON("/api/quality"), getJSON("/api/data-status")]); hideState(); $("#dq").hidden = false;
    const g = q.gate, d = g.duplicates;
    $("#dq-kpis").innerHTML = [kpi("Rows in source", fmt(g.row_count), `${g.column_count} columns`), kpi("Missing coordinates", g.missing_coordinate_pct + "%", `${g.missing_coordinate_count} rows`),
      kpi("Duplicate rows", fmt(d.exact_duplicate_rows_raw_all_columns), "exact, all columns · source has no request id"), kpi("Shared exact coordinate", fmt(d.pothole_reports_sharing_exact_coordinate_with_another_pothole_report), "pothole reports (repeat ≠ duplicate)"),
      kpi("Inside boundary", g.bengaluru_coverage.rows_inside_boundary_pct + "%", "BBMP 2015 ward union"), kpi("Months with data", g.months_with_data, `${day(g.date_min)} → ${day(g.date_max)}`)].join("");
    barChart($("#chart-dq"), q.monthly, { x: "month", y: "pothole_reports", ytitle: "pothole reports" });
    const cq = $("#cq tbody"); q.coordinate_quality.filter((r) => r.scope === "pothole_reports").forEach((r) => { const tr = document.createElement("tr"); [r.check, r.count, r.pct].forEach((v, i) => { const td = document.createElement("td"); if (i === 0) td.className = "l"; td.textContent = v; tr.appendChild(td); }); cq.appendChild(tr); });
    const ct = $("#cat tbody"); q.categories.slice(0, 18).forEach((r) => { const tr = document.createElement("tr"); [r.category_title, r.sub_category_title, r.count, r.included_as_pothole ? "included" : ""].forEach((v, i) => { const td = document.createElement("td"); if (i < 2) td.className = "l"; td.textContent = v ?? "(missing)"; tr.appendChild(td); }); ct.appendChild(tr); });
    const s = st.secondary; $("#sec").innerHTML = s && s.fms_records ? `<p>${fmt(s.fms_inside_bengaluru_boundary)} Fix My Street pothole records (${day(s.fms_date_min)} → ${day(s.fms_date_max)}) vs ${s.icmyc_pothole_reports_same_months_inside_boundary} iCMyC pothole complaints in the same months. Ward-level Spearman ρ = ${s.spearman_ward_counts?.rho}. Fix My Street density is ${s.density_ratio_inside_vs_elsewhere}× higher inside iCMyC cluster footprints than elsewhere (${s.fms_density_inside_icmyc_cluster_footprints_per_km2} vs ${s.fms_density_elsewhere_per_km2} per km²).</p><p class="muted">Not merged with the primary dataset.</p>` : "<p class='state empty'>Secondary dataset not available.</p>";
  },
};

document.addEventListener("DOMContentLoaded", () => {
  provenance();
  const fn = pages[document.body.dataset.page];
  if (fn) fn().catch(fail);
});
