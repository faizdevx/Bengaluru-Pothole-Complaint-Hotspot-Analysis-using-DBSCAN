"use strict";
(async function () {
  try {
    setState("Loading map data…");
    const [cl, sp, grid] = await Promise.all([getJSON("/api/clusters"), getJSON("/api/spatial-units?geometry=true"), getJSON("/api/grid")]);
    hideState(); $("#maplayout").hidden = false;
    const map = L.map("map", { preferCanvas: true }).setView([12.9716, 77.5946], 11);
    const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap contributors" }).addTo(map);
    const byId = Object.fromEntries(sp.units.map((u) => [u.unit_id, u]));
    const metric = () => $("#ward-metric").value;
    const val = (u) => metric() === "density" ? u.total_reports / u.area_km2 : metric() === "share" ? (u.pothole_share ?? 0) : u.total_reports;
    const vals = sp.units.map(val).sort((a, b) => a - b);
    const ramp = ["#f3f7fb", "#cfe0ee", "#9ec3de", "#5f9bc7", "#2b6f9e", "#154a73"];
    const brk = () => [0.2, 0.4, 0.6, 0.8, 0.95].map((q) => vals[Math.floor(q * (vals.length - 1))]);
    const colour = (v) => { const b = brk(); let i = 0; while (i < b.length && v > b[i]) i++; return ramp[i]; };
    const nm = (v) => metric() === "share" ? (v * 100).toFixed(0) + "%" : v.toFixed(1);
    function legend() { const b = brk(); $("#legend").innerHTML = ramp.map((c, i) => `<span><i style="background:${c}"></i>${i === 0 ? "≤ " + nm(b[0]) : i === b.length ? "> " + nm(b[b.length - 1]) : nm(b[i - 1]) + "–" + nm(b[i])}</span>`).join(""); }
    const wardLayer = L.geoJSON(Object.entries(sp.geometries).map(([n, g]) => ({ type: "Feature", properties: { id: +n }, geometry: g.geometry })), {
      style: (f) => ({ color: "#8a97a6", weight: 0.6, fillColor: colour(val(byId[f.properties.id])), fillOpacity: 0.55 }),
      onEachFeature: (f, l) => { const u = byId[f.properties.id]; l.bindTooltip(`${u.ward_name}: ${u.total_reports} pothole complaints of ${u.all_complaints} (${u.pothole_share != null ? (u.pothole_share * 100).toFixed(0) : "—"}%)`, { sticky: true }); },
    }).addTo(map);
    const persist = L.geoJSON(Object.entries(sp.geometries).filter(([n]) => byId[n]?.persistent).map(([n, g]) => ({ type: "Feature", geometry: g.geometry })), { style: { color: "#c46b2d", weight: 2.5, fill: false } });
    legend();
    $("#ward-metric").addEventListener("change", () => { wardLayer.setStyle((f) => ({ color: "#8a97a6", weight: 0.6, fillColor: colour(val(byId[f.properties.id])), fillOpacity: 0.55 })); legend(); });

    const polys = { type: "FeatureCollection", features: cl.features.filter((f) => f.geometry.type === "Polygon") };
    const cents = { type: "FeatureCollection", features: cl.features.filter((f) => f.geometry.type === "Point") };
    const popup = (p) => `<strong>Cluster #${esc(p.cluster_id)}</strong><dl><dt>Reports</dt><dd>${p.reports}</dd><dt>Approx. radius</dt><dd>${fmt(p.radius_m)} m</dd><dt>First report</dt><dd>${day(p.date_min)}</dd><dt>Latest report</dt><dd>${day(p.date_max)}</dd><dt>Spatial density</dt><dd>${fmt(p.density_per_km2, 1)} reports/km²</dd><dt>Persistence</dt><dd>${p.persistence == null ? "Unavailable" : `${p.active_months}/${p.eligible_months} months active`}</dd></dl>`;
    const info = (p) => { $("#cluster-info").innerHTML = `${popup(p)}<p><a href="/clusters?id=${p.cluster_id}">Open in Cluster Explorer</a></p>`; };
    const pick = (f, l) => { l.bindPopup(popup(f.properties)); l.on("click", () => info(f.properties)); };
    const clusterLayer = L.geoJSON(polys, { style: { color: "#b3402f", weight: 2, fillColor: "#e5806f", fillOpacity: 0.35 }, onEachFeature: pick }).addTo(map);
    const centLayer = L.geoJSON(cents, { pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 3 + Math.sqrt(f.properties.reports), color: "#7a2418", fillColor: "#b3402f", fillOpacity: 0.9, weight: 1 }), onEachFeature: pick }).addTo(map);
    const cell = (c, key, col) => L.rectangle([[c.lat - 0.0011, c.lon - 0.0012], [c.lat + 0.0011, c.lon + 0.0012]], { color: col, weight: 0.5, fillColor: col, fillOpacity: Math.min(0.2 + 0.15 * c[key], 0.85) }).bindTooltip(`${c[key]} report(s) in this 250 m cell`);
    const gridLayer = L.layerGroup(grid.cells.filter((c) => c.clustered > 0).map((c) => cell(c, "clustered", "#8e3b9e")));
    const noiseLayer = L.layerGroup(grid.cells.filter((c) => c.noise > 0).map((c) => cell(c, "noise", "#6b7480")));
    const link = (id, layer) => $(id).addEventListener("change", (e) => (e.target.checked ? layer.addTo(map) : map.removeLayer(layer)));
    link("#l-clusters", clusterLayer); link("#l-centroids", centLayer); link("#l-wards", wardLayer); link("#l-persist", persist); link("#l-grid", gridLayer); link("#l-noise", noiseLayer); link("#l-tiles", tiles);
    if (polys.features.length) map.fitBounds(L.geoJSON(polys).getBounds().pad(0.05));
    wardLayer.bringToBack();
    window.__map = map; window.__mapReady = true;
  } catch (e) { fail(e); }
})();
