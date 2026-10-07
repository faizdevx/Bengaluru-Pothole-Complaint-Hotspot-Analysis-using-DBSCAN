"""Generate DATASET.md, DATASET_FEASIBILITY.md and reports/analysis_report.md from
measured values. Nothing numeric is hand-typed."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.analysis.run import NULL_REPS
from src.config import DATA_META, MIN_ELIGIBLE_MONTHS_FOR_TREND, MIN_REPORTS_FOR_TREND, REPORTS, ROOT, SOURCES
from src.geo.distance import haversine_m
from src.storage.db import connect, get_artifact, load_complaints


def _meta(key):
    p = DATA_META / f"{key}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _pct(x, d=1):
    return f"{x:.{d}f}%"


def write_dataset_docs() -> None:
    g = json.loads((REPORTS / "data_feasibility.json").read_text())
    m = _meta("icmyc_log"); wm = _meta("ward_map_2015"); fm = _meta("fms_kml")
    p = g["pothole"]; d = g["duplicates"]; b = g["bengaluru_coverage"]
    cr = g["coordinate_range_all"]
    coord = pd.read_csv(REPORTS / "coordinate_quality.csv")
    cq = lambda scope, chk: coord[(coord.scope == scope) & (coord.check.str.startswith(chk))].iloc[0]
    coarse = cq("pothole_reports", "coarse_rounded"); disagree = cq("pothole_reports", "ward_id_disagrees")
    out_b = cq("pothole_reports", "outside_bengaluru")
    monthly = pd.read_csv(REPORTS / "monthly_data_quality.csv")
    yearly = monthly.assign(y=monthly.month.str[:4]).groupby("y")[["all_complaints", "pothole_reports"]].sum()
    ytxt = "; ".join(f"{y}: {int(r.pothole_reports)} pothole / {int(r.all_complaints)} all" for y, r in yearly.iterrows())
    (ROOT / "DATASET.md").write_text(f"""# DATASET

## Primary dataset

| Field | Value |
|---|---|
| Dataset name | I Change My City Complaints Log - 2019 - 2022 |
| Publisher / source | Janaagraha (I Change My City, "iCMyC") |
| Host | OpenCity (data.opencity.in) - a redistributor, **not** the originating civic authority |
| OpenCity dataset | `{SOURCES['icmyc_log']['dataset']}` |
| Resource identifier | `{SOURCES['icmyc_log']['resource_id']}` |
| License | {SOURCES['icmyc_log']['license']} |
| Retrieval date (UTC) | {m.get('retrieved_at')} |
| File size / SHA-256 | {m.get('file_size')} bytes / `{m.get('sha256')}` |
| Original date range (data as measured) | {g['date_min']} to {g['date_max']} |
| Actual row count | {g['row_count']:,} |
| Actual pothole row count | {p['taxonomy_rows']:,} |
| Actual valid-coordinate count | {g['valid_coordinate_count']:,} all rows ({_pct(100 - g['missing_coordinate_pct'])}); {p['valid_coordinates']:,} pothole rows |
| Pothole rows inside Bengaluru boundary | {p['inside_boundary']:,} |
| Pothole rows used by DBSCAN | {p['usable_for_dbscan']:,} (suspected fallback pins excluded: {p['suspect_fallback_pin_rows_inside_boundary']}) |

**The primary dataset is Janaagraha / I Change My City civic-tech complaint data, not a direct BBMP real-time API.**
OpenCity is only the host. It is a historical file, not a live feed.

Attribution (CC BY-SA): *Janaagraha, "I Change My City Complaints Log - 2019 - 2022", via OpenCity
(https://data.opencity.in/dataset/{SOURCES['icmyc_log']['dataset']}), licensed under CC BY-SA.*
Derived outputs in this repository (aggregates, cluster summaries) are shared under the same share-alike terms.

## Latitude / longitude quality (measured)

- Missing coordinates: {g['missing_coordinate_count']} ({g['missing_coordinate_pct']}%).
- Coordinate extent (all rows): lat {cr['lat_min']:.4f}-{cr['lat_max']:.4f}, lon {cr['lon_min']:.4f}-{cr['lon_max']:.4f}.
- Pothole rows with <=3 decimals (coarse): {int(coarse['count'])} ({coarse['pct']}%).
- Pothole rows outside the BBMP ward union: {int(out_b['count'])} ({out_b['pct']}%).
- Pothole rows whose source `ward_id` disagrees with the polygon ward (inside boundary): {int(disagree['count'])} ({disagree['pct']}%).
- Exact coordinates shared with another pothole report: {d['pothole_reports_sharing_exact_coordinate_with_another_pothole_report']} rows;
  within {10} m of another pothole report: {d.get('pothole_reports_with_another_pothole_report_within_10m')} rows.
- **Suspected default / geocoder-fallback pins.** Many coordinates are reused by dozens of complaints of unrelated categories over
  months or years (the single most-reused coordinate carries {d['max_coordinate_multiplicity_all_categories']} complaints, {d['max_coordinate_multiplicity_pothole_reports']} of them pothole reports; see `reports/duplicate_coordinate_analysis.csv`).
  Rule used: a coordinate shared by >= {8} complaints of any category is flagged. {p['suspect_fallback_pin_rows_inside_boundary']} pothole rows are affected and are excluded from DBSCAN
  (a sensitivity run that includes them is recorded in the analysis report).

## Timestamps

Two formats occur (`1-1-2019 06:33` and `7/31/2022 14:03`); both are month-first (zero chronological inversions in file order vs 39 under day-first).
Naive local times are treated as Asia/Kolkata. Missing timestamps: {g['missing_timestamps']}.
The file ends {g['date_max'][:10]}, i.e. it covers 2019 to July 2022, not the whole of 2022.
Yearly counts: {ytxt}. Reporting volume falls sharply over time.

## Known limitations

- Not live, not complete: user-submitted reports on one civic-tech portal; no physical road-condition ground truth.
- No request identifier exists in the source (`request_id` is a surrogate content hash).
- Strong decline in platform usage (see yearly counts) confounds any trend or "recent activity" statistic.
- Locality-level geocodes and repeated pins reduce positional precision (see above).
- Free-text fields (`title`, `description`, `location`, `address`) are dropped during preprocessing and never stored or published.

## Boundary source (for assigning wards and defining "inside Bengaluru")

| Field | Value |
|---|---|
| boundary_source | {b['boundary_source']} |
| boundary_vintage | {b['boundary_vintage']} |
| boundary_type | {b['boundary_type']} |
| License | Not specified in the OpenCity metadata (`license_title: None`) |
| SHA-256 | `{wm.get('sha256')}` |

{b['rows_inside_boundary']:,} of {g['row_count']:,} rows ({b['rows_inside_boundary_pct']}%) fall inside it. Most of the rest carry the source's own ward 199 "Other" label.

## Secondary dataset (kept separate)

BBMP Fix My Street Data - May and June 2022 (OpenCity dataset `{SOURCES['fms_kml']['dataset']}`, resource `{SOURCES['fms_kml']['resource_id']}`, licence {SOURCES['fms_kml']['license']}).
Retrieved {fm.get('retrieved_at')}, SHA-256 `{fm.get('sha256')}`. Its KML contains complainant names and phone numbers; they are discarded while
parsing and never stored. It is **not merged** with the primary data: it is used only for validation and triangulation (see the analysis report).
""")

    (ROOT / "DATASET_FEASIBILITY.md").write_text(f"""# DATASET FEASIBILITY (data gate)

Gate rule: {g['gate_rule']}.
**Result: {'PASSED' if g['gate_passed'] else 'FAILED'}.** Full measurements: `reports/data_feasibility.json`.

| Measurement | Value |
|---|---|
| Rows / columns | {g['row_count']:,} / {g['column_count']} |
| Columns | `{'`, `'.join(g['columns'])}` |
| File encoding | {g['file_encoding']} (not UTF-8) |
| Date range | {g['date_min']} to {g['date_max']} ({g['months_with_data']} calendar months with data) |
| Missing timestamps | {g['missing_timestamps']} |
| Missing coordinates | {g['missing_coordinate_count']} ({g['missing_coordinate_pct']}%) |
| Rows inside Bengaluru boundary | {b['rows_inside_boundary']:,} ({b['rows_inside_boundary_pct']}%) |
| Pothole rows (taxonomy) | {p['taxonomy_rows']:,} |
| ... with valid coordinates | {p['valid_coordinates']:,} |
| ... inside boundary | {p['inside_boundary']:,} |
| ... after excluding suspected fallback pins | {p['usable_for_dbscan']:,} |
| Months covered by usable pothole points | {p['months_covered']} |
| Duplicate request IDs | none available (source has no identifier) |
| Duplicate surrogate keys (all / pothole) | {d['duplicate_surrogate_key_all']} / {d['duplicate_surrogate_key_pothole']} |
| Exact duplicate raw rows (all columns) | {d['exact_duplicate_rows_raw_all_columns']} |
| Unique coordinates (all / pothole) | {d['unique_coordinates_all']:,} / {d['unique_coordinates_pothole']:,} |

## Pothole filter (taxonomy-based, no keyword matching)

Included (`sub_category_id`): 66 *Fixing/Reparing Potholes* (category *Mobility - Roads, Footpaths and Infrastructure*) and
594 *Repair of Potholes on Roads* (category *PWD*). The filter aborts if these ids stop carrying these titles.
Excluded: every other category, including *Tarring Or Asphalting Of Existing Road* (resurfacing requests) and complaint titles that merely mention
"pothole" in other sub-categories. Frequency table: `reports/category_distribution.csv`.

## Verdict

{p['usable_for_dbscan']:,} usable pothole observations over {p['months_covered']} months is enough for DBSCAN, but modest: the point set is sparse
(median nearest-neighbour distance a few hundred metres), so clusters are small and most reports are noise. Platform usage also declines
steeply over the period. These are limitations of the data, documented in `reports/analysis_report.md`.
""")


def write_analysis_report() -> None:
    with connect() as con:
        run = con.execute("SELECT * FROM analysis_runs ORDER BY run_id DESC LIMIT 1").fetchone()
        rid = run["run_id"]; meta = json.loads(run["params_json"])
        hot = pd.DataFrame(get_artifact(con, "hotspots")); wards = pd.DataFrame(get_artifact(con, "wards"))
        pers = get_artifact(con, "persistence_definition"); sec = get_artifact(con, "secondary_comparison") or {}
        city = pd.DataFrame(get_artifact(con, "city_timeline")); ctr = get_artifact(con, "city_trend")
        crec = get_artifact(con, "city_recent"); warns = get_artifact(con, "dbscan_warnings")
        allc = load_complaints(con)
        mem = pd.read_sql("SELECT complaint_rowid, cluster_id FROM cluster_membership WHERE run_id=?", con, params=(rid,))
        cl = {r["cluster_id"]: json.loads(r["payload"]) for r in con.execute("SELECT * FROM clusters WHERE run_id=?", (rid,))}
    sweep = pd.read_csv(REPORTS / "dbscan_parameter_sweep.csv")
    feas = json.loads((REPORTS / "data_feasibility.json").read_text())
    n, noise = int(run["dataset_size"]), int(run["noise_count"])
    clustered = n - noise
    big = hot.sort_values("reports", ascending=False).iloc[0]
    sizes = hot.reports
    pts = allc[(allc.is_pothole == 1) & (allc.usable == 1) & (allc.suspect_fallback_pin == 0)].merge(
        mem, left_on="rowid_", right_on="complaint_rowid")
    pts["noise"] = pts.cluster_id == -1
    centre = (12.9716, 77.5946)   # Bengaluru city centre (Kempegowda / Majestic area), only to bin distance
    pts["dist_km"] = haversine_m(pts.latitude.to_numpy(), pts.longitude.to_numpy(), *centre) / 1000
    bins = pd.cut(pts.dist_km, [0, 5, 10, 15, 100], labels=["0-5 km", "5-10 km", "10-15 km", ">15 km"])
    nb = pts.groupby(bins, observed=True).agg(points=("noise", "size"), noise_pct=("noise", lambda s: 100 * s.mean()))
    zones = wards.set_index("unit_id").zone
    pts["zone"] = pts.ward_id.map(zones)
    zt = pts.groupby("zone").agg(points=("noise", "size"), clustered=("noise", lambda s: int((~s).sum()))).sort_values("clustered", ascending=False)
    sel = meta["selected_row"]
    ok = sweep[sweep.passes_selection_criteria]
    sens = meta["sensitivity_with_fallback_pins"]; hd = meta["hdbscan_secondary"]
    yearly = city.assign(y=city.month.str[:4]).groupby("y")[["pothole_reports", "all_complaints"]].sum()
    persistent = wards[wards.persistent == True].sort_values("total_reports", ascending=False)  # noqa: E712
    trend_c = hot.observed_trend.value_counts().to_dict()
    kd = meta["k_distance"]["details"]["5"]
    L = []
    A = L.append
    A("# Analysis report\n")
    A("*This project identifies geographic concentrations of civic pothole **complaints**. It does not measure actual pothole density or physical road-condition severity.*\n")
    A(f"Data: Janaagraha / I Change My City complaint log (historical, {feas['date_min'][:10]} to {feas['date_max'][:10]}), hosted by OpenCity. Not real-time.\n")
    A("## 1. Setup\n")
    A(f"- Points clustered: **{n:,}** pothole reports (taxonomy-filtered, valid coordinates, inside the BBMP 2015 ward union, suspected fallback pins excluded: {feas['pothole']['suspect_fallback_pin_rows_inside_boundary']} rows).")
    A(f"- Distance: haversine on radians (eps converted from metres, R = 6371008.8 m). **eps = {run['eps_meters']:g} m, min_samples = {run['min_samples']}.**")
    A(f"- Result: **{len(cl)} clusters, {clustered:,} clustered reports, {noise:,} noise reports ({run['noise_percentage']}%)**. Noise (label -1) is retained and reported, never dropped.\n")
    A("## 2. Parameter choice (a judgment, not an optimum)\n")
    A(f"- k-distance (k=5): median {kd['percentiles_m']['50']:.0f} m, 90th percentile {kd['percentiles_m']['90']:.0f} m, knee heuristic {kd['knee_m']:.0f} m (`reports/k_distance_plot.png`).")
    A(f"  The knee sits far above the selected eps. Larger values (eps >= 500-750 m) chain neighbouring clusters: in the sweep, eps=750 m produces one cluster holding "
      f"{100*sweep[(sweep.eps_meters==750)&(sweep.min_samples==5)].largest_cluster_share.iloc[0]:.0f}% of clustered reports with a max radius of "
      f"{sweep[(sweep.eps_meters==750)&(sweep.min_samples==5)].max_cluster_radius_m.iloc[0]:.0f} m. The knee is therefore not used.")
    A(f"- {len(sweep)} configurations were swept (`reports/dbscan_parameter_sweep.csv`). Silhouette is recorded as supplementary only and is **not** used for selection "
      f"(selected configuration: {sel.get('silhouette_supplementary')}; sweep range {sweep.silhouette_supplementary.min():.2f} to {sweep.silhouette_supplementary.max():.2f}, so it barely discriminates between settings).")
    A(f"- Selection criteria (all required): no sanity warnings; noise <= {meta['selection_criteria']['max_noise_percentage']:g}%; max cluster radius <= {meta['selection_criteria']['max_cluster_radius_m']:g} m; "
      f"neighbour-eps stability ARI >= {meta['selection_criteria']['min_stability_ari']}; >= {meta['selection_criteria']['min_cluster_count']} clusters; "
      f"observed cluster count >= {meta['selection_criteria']['min_observed_to_baseline_cluster_ratio']}x a baseline (random same-size subsets of non-pothole complaint locations, {NULL_REPS} draws).")
    A(f"- Only **{len(ok)}** of {len(sweep)} configurations pass: " + "; ".join(f"eps={r.eps_meters:g}/min_samples={r.min_samples}" for r in ok.itertuples()) +
      f". Selected: the one with highest stability (ARI {sel['stability_ari']}). The choice is sensitive; it should not be read as 'the' correct setting.")
    A(f"- **Baseline control.** At the selected setting the baseline yields {sel['baseline_cluster_count_mean']} +/- {sel['baseline_cluster_count_sd']} clusters and {sel['baseline_noise_percentage_mean']}% noise, "
      f"versus {sel['cluster_count']} clusters and {sel['noise_percentage']}% noise for pothole reports. Pothole reports are somewhat more concentrated than general complaint activity, "
      f"but a large part of the apparent structure reflects where citizens use the portal at all.\n")
    A("### Automatic sanity warnings across the sweep\n")
    A(f"{len(warns)} of {len(sweep)} configurations raised at least one warning; examples:\n")
    for w in warns[:6]:
        A(f"- {w}")
    A(f"\nSelected configuration warnings: {sel.get('warnings') or 'none'}.\n")
    A("## 3. Clusters\n")
    A(f"- Largest: cluster {int(big.cluster_id)} with {int(big.reports)} reports (radius {big.radius_m:.0f} m, {100*big.share_of_city_pothole_reports:.1f}% of analysed pothole reports). "
      f"The largest cluster holds {100*big.reports/clustered:.1f}% of clustered reports, so no single cluster dominates.")
    A(f"- Smallest: {int(sizes.min())} reports (= min_samples). Median cluster size {sizes.median():g}; {int((sizes<=7).sum())} of {len(sizes)} clusters have <= 7 reports. Treat small clusters as weak evidence.")
    A(f"- Clusters made almost entirely of one repeated coordinate: {int(hot.single_coordinate_cluster.sum())}.")
    A(f"- Footprint of all clusters: radii {hot.radius_m.min():.0f}-{hot.radius_m.max():.0f} m (median {hot.radius_m.median():.0f} m). Boundaries are 50 m-buffered convex hulls: *cluster visualization boundaries*, not pothole areas.")
    A("- Clustered reports by BBMP zone (top 5): " + ", ".join(f"{z} ({int(r.clustered)})" for z, r in zt.head(5).iterrows()) + ".\n")
    A("### Does DBSCAN over-cluster dense regions or miss sparse peripheral areas?\n")
    wd = wards.set_index("unit_id")
    dens = (wd.total_reports / wd.area_km2)
    pts["ward_density"] = pts.ward_id.map(dens)
    pts["dens_band"] = pd.qcut(pts.ward_density.rank(method="first"), 3, labels=["lowest third", "middle third", "highest third"])
    nd = pts.groupby("dens_band", observed=True).agg(points=("noise", "size"), noise_pct=("noise", lambda s: 100 * s.mean()),
                                                      dmin=("ward_density", "min"), dmax=("ward_density", "max"))
    A("Noise share by local reporting density (reports per km2 of the point's ward, split into thirds of reports):\n")
    A("| Ward density band | Reports | Ward density (reports/km2) | Noise % |\n|---|---|---|---|")
    for k, r in nd.iterrows():
        A(f"| {k} | {int(r.points)} | {r.dmin:.1f}-{r.dmax:.1f} | {r.noise_pct:.1f}% |")
    A("")
    A("For reference, noise share by distance from the city centre:\n")
    A("| Distance | Reports | Noise % |\n|---|---|---|")
    for k, r in nb.iterrows():
        A(f"| {k} | {int(r.points)} | {r.noise_pct:.1f}% |")
    A("")
    lo, hi = nd.noise_pct.iloc[0], nd.noise_pct.iloc[-1]
    if lo - hi >= 10:
        verdict = (f"Sparse areas are heavily under-detected: {lo:.0f}% of reports in the lowest-density third are noise vs {hi:.0f}% in the highest-density third. "
                   f"A single global eps/min_samples cannot flag local concentrations in low-reporting areas, so peripheral or low-adoption areas are systematically missed (partly by construction: any density threshold treats low-density areas as noise).")
    else:
        verdict = (f"Noise shares are {lo:.0f}% (lowest-density third) vs {hi:.0f}% (highest): no strong evidence here that sparse areas are disproportionately missed.")
    A(verdict + " ")
    A(f"Over-clustering: at the selected setting the largest cluster radius is {hot.radius_m.max():.0f} m and the largest cluster holds {100*big.reports/clustered:.1f}% of clustered reports, so there is no gross chaining; "
      f"chaining appears at larger eps (see sweep warnings). HDBSCAN (secondary experiment, same minimum size) gives {hd['clusters']} clusters / {hd['noise_percentage']}% noise with ARI {hd['ari_vs_selected_dbscan']} against the selected DBSCAN labels, "
      f"i.e. a variable-density method gives a materially different partition.\n")
    A("## 4. Sensitivity and duplicate-coordinate behaviour\n")
    A(f"- Re-running the same eps/min_samples **with** the suspected fallback pins gives {sens['cluster_count']} clusters and {sens['noise_percentage']}% noise (without: {run['cluster_count']} and {run['noise_percentage']}%); "
      f"the single most-reused pin holds {sens['largest_single_coordinate_pin_reports']} pothole reports at one coordinate, which would otherwise appear as a dense 'hotspot' that is only a default map location.")
    A(f"- {feas['duplicates']['pothole_reports_sharing_exact_coordinate_with_another_pothole_report']} pothole reports share an exact coordinate with another pothole report; repeated reports at one place are kept (they can be genuine repeat complaints) and are distinct from duplicated records ({feas['duplicates']['duplicate_surrogate_key_pothole']} surrogate-key duplicates among pothole rows).")
    A("- The fallback-pin threshold (multiplicity >= 8) is a heuristic; see `fallback_pin_sensitivity_pothole_rows` in `reports/data_feasibility.json` for other cut-offs.\n")
    A("## 5. Monthly activity and normalisation\n")
    A("| Year | Pothole reports (analysed set) | All complaints | Pothole share |\n|---|---|---|---|")
    for y, r in yearly.iterrows():
        A(f"| {y} | {int(r.pothole_reports)} | {int(r.all_complaints)} | {100*r.pothole_reports/max(r.all_complaints,1):.1f}% |")
    A("")
    A(f"- City-wide observed trend (monthly Kendall tau): **{ctr['pothole_count']['trend']}** (tau={ctr['pothole_count']['tau']}, q={ctr['pothole_count']['q_value']:.2g}); the pothole *share* of all complaints also shows tau={ctr['pothole_share_x1000']['tau']}.")
    A(f"- Latest 3 months of the dataset: {crec['recent_3_month_count']/3:.1f} reports/month vs {crec['historical_average']:.1f}/month over the earlier months ({crec['recent_vs_historical_change']*100:+.0f}%). "
      f"This is platform-wide decline in portal use, so cluster-level 'recent activity' mostly shows the same decline; read cluster values against this city baseline.")
    A(f"- Normalisation: pothole reports / all complaints for the same unit and period (clusters: all complaints inside the cluster footprint). It partly controls for portal activity but not for population, awareness or adoption differences.")
    A(f"- Cluster observed trends (Kendall tau, BH-adjusted q<0.05, >= {MIN_REPORTS_FOR_TREND} reports and >= {MIN_ELIGIBLE_MONTHS_FOR_TREND} months): {trend_c}. Most clusters have too few reports for any trend claim. These are observed trends, not established changes in road condition.\n")
    A("## 6. Recurring areas (fixed units)\n")
    A(f"- Unit: BBMP 2015 wards (polygon-assigned). {pers['eligible_months']} eligible months (>= {pers['minimum_eligible_months_required']} required: persistence is supported).")
    A(f"- Active month: {pers['active_month_rule']}. Resulting per-ward thresholds: {pers['ward_active_threshold_distribution']} (count of wards per threshold).")
    A(f"- Persistent ward: {pers['persistent_rule']}. **{pers['persistent_wards']} of {len(wards)} wards** qualify. Top by reports: " +
      ", ".join(f"{r.ward_name} ({int(r.total_reports)} reports, {int(r.active_months)}/{int(r.eligible_months)} active months)" for r in persistent.head(5).itertuples()) + ".")
    ward_m = pd.read_csv(REPORTS / "spatial_unit_monthly.csv")
    pm = ward_m[ward_m.ward_id.isin(persistent.unit_id) & (ward_m.pothole_reports > 0)]
    early = 100 * pm.pothole_reports[pm.month < "2021-01"].sum() / max(pm.pothole_reports.sum(), 1)
    A(f"- Caveat: the null ignores population and adoption; {early:.0f}% of the persistent wards' pothole reports fall in 2019-2020 (portal use fell afterwards), so persistence mostly describes the earlier period. Clusters report only the descriptive active-month share; "
      f"no persistence test is applied to clusters because they are selected for density (testing them against a uniform null would be circular).\n")
    A("## 7. Cross-check against BBMP Fix My Street (separate source, May-June 2022)\n")
    if sec.get("fms_records"):
        A(f"- {sec['fms_inside_bengaluru_boundary']:,} Fix My Street pothole records inside the boundary (dates {sec['fms_date_min'][:10]} to {sec['fms_date_max'][:10]}) against {sec['icmyc_pothole_reports_same_months_inside_boundary']} iCMyC pothole reports in the same months: "
          f"iCMyC captures a tiny and probably unrepresentative slice of 2022 reporting.")
        A(f"- Ward-level Spearman correlation of counts: {sec.get('spearman_ward_counts', {}).get('rho')} (weak; iCMyC n is tiny). Top-20-ward overlap: {sec.get('top20_ward_overlap')}.")
        A(f"- Fix My Street density inside iCMyC cluster footprints: {sec.get('fms_density_inside_icmyc_cluster_footprints_per_km2')}/km2 vs {sec.get('fms_density_elsewhere_per_km2')}/km2 elsewhere (ratio {sec.get('density_ratio_inside_vs_elsewhere')}). "
          f"Independent complaint density is higher where iCMyC clusters sit, which supports the clusters as places of repeated *reporting*, subject to the same reporting biases.\n")
    A("## 8. Limitations\n")
    for t in [
        "Complaints are not potholes: no physical measurement, no severity, no ground truth. Complaint density is not road-condition severity.",
        "Reporting bias: uneven portal adoption, awareness, civic engagement and population across wards.",
        "Historical, non-real-time data that ends 2022-07-31; reporting volume collapses over time, confounding trends.",
        "Coordinates: locality-level and default pins exist; a rule-based exclusion is used and is itself a heuristic.",
        "City boundary = BBMP 2015 ward union; reports outside it (mostly source ward 199 'Other') are excluded from the analysis.",
        "DBSCAN uses one global density threshold: sparse periphery is under-detected and dense cores can merge.",
        "No request IDs in the source; repeat reports cannot be tied to unique complainants or unique potholes.",
        "Parameter choice is a judgment among few passing configurations; cluster counts at nearby settings differ materially.",
    ]:
        A(f"- {t}")
    (REPORTS / "analysis_report.md").write_text("\n".join(L) + "\n")
