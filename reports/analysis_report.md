# Analysis report

*This project identifies geographic concentrations of civic pothole **complaints**. It does not measure actual pothole density or physical road-condition severity.*

Data: Janaagraha / I Change My City complaint log (historical, 2019-01-01 to 2022-07-31), hosted by OpenCity. Not real-time.

## 1. Setup

- Points clustered: **1,982** pothole reports (taxonomy-filtered, valid coordinates, inside the BBMP 2015 ward union, suspected fallback pins excluded: 113 rows).
- Distance: haversine on radians (eps converted from metres, R = 6371008.8 m). **eps = 250 m, min_samples = 5.**
- Result: **76 clusters, 586 clustered reports, 1,396 noise reports (70.43%)**. Noise (label -1) is retained and reported, never dropped.

## 2. Parameter choice (a judgment, not an optimum)

- k-distance (k=5): median 427 m, 90th percentile 901 m, knee heuristic 910 m (`reports/k_distance_plot.png`).
  The knee sits far above the selected eps. Larger values (eps >= 500-750 m) chain neighbouring clusters: in the sweep, eps=750 m produces one cluster holding 33% of clustered reports with a max radius of 9779 m. The knee is therefore not used.
- 60 configurations were swept (`reports/dbscan_parameter_sweep.csv`). Silhouette is recorded as supplementary only and is **not** used for selection (selected configuration: 0.759; sweep range -0.38 to 1.00, so it barely discriminates between settings).
- Selection criteria (all required): no sanity warnings; noise <= 75%; max cluster radius <= 1000 m; neighbour-eps stability ARI >= 0.6; >= 20 clusters; observed cluster count >= 1.5x a baseline (random same-size subsets of non-pothole complaint locations, 20 draws).
- Only **3** of 60 configurations pass: eps=200/min_samples=4; eps=250/min_samples=5; eps=300/min_samples=6. Selected: the one with highest stability (ARI 0.734). The choice is sensitive; it should not be read as 'the' correct setting.
- **Baseline control.** At the selected setting the baseline yields 48.4 +/- 6.2 clusters and 83.7% noise, versus 76 clusters and 70.43% noise for pothole reports. Pothole reports are somewhat more concentrated than general complaint activity, but a large part of the apparent structure reflects where citizens use the portal at all.

### Automatic sanity warnings across the sweep

34 of 60 configurations raised at least one warning; examples:

- WARNING: largest cluster radius is 4245 m (geographically huge).
- WARNING: largest cluster radius is 9578 m (geographically huge).
- WARNING: eps=1000 m, min_samples=3 creates one cluster containing 91% of clustered reports. Review parameter choice. | WARNING: largest cluster radius is 15345 m (geographically huge).
- WARNING: eps=75 m, min_samples=4 labels 89.05% of reports as noise (almost everything is noise).
- WARNING: eps=100 m, min_samples=4 labels 85.52% of reports as noise (almost everything is noise).
- WARNING: largest cluster radius is 4245 m (geographically huge).

Selected configuration warnings: none.

## 3. Clusters

- Largest: cluster 47 with 23 reports (radius 326 m, 1.2% of analysed pothole reports). The largest cluster holds 3.9% of clustered reports, so no single cluster dominates.
- Smallest: 5 reports (= min_samples). Median cluster size 6; 45 of 76 clusters have <= 7 reports. Treat small clusters as weak evidence.
- Clusters made almost entirely of one repeated coordinate: 1.
- Footprint of all clusters: radii 0-638 m (median 231 m). Boundaries are 50 m-buffered convex hulls: *cluster visualization boundaries*, not pothole areas.
- Clustered reports by BBMP zone (top 5): Mahadevapura (239), Bommanahalli  (172), East (63), Yelahanka (44), South (37).

### Does DBSCAN over-cluster dense regions or miss sparse peripheral areas?

Noise share by local reporting density (reports per km2 of the point's ward, split into thirds of reports):

| Ward density band | Reports | Ward density (reports/km2) | Noise % |
|---|---|---|---|
| lowest third | 661 | 0.2-3.2 | 86.8% |
| middle third | 660 | 3.2-5.5 | 72.3% |
| highest third | 661 | 5.5-14.3 | 52.2% |

For reference, noise share by distance from the city centre:

| Distance | Reports | Noise % |
|---|---|---|
| 0-5 km | 243 | 77.8% |
| 5-10 km | 815 | 77.4% |
| 10-15 km | 817 | 60.2% |
| >15 km | 107 | 78.5% |

Sparse areas are heavily under-detected: 87% of reports in the lowest-density third are noise vs 52% in the highest-density third. A single global eps/min_samples cannot flag local concentrations in low-reporting areas, so peripheral or low-adoption areas are systematically missed (partly by construction: any density threshold treats low-density areas as noise). 
Over-clustering: at the selected setting the largest cluster radius is 638 m and the largest cluster holds 3.9% of clustered reports, so there is no gross chaining; chaining appears at larger eps (see sweep warnings). HDBSCAN (secondary experiment, same minimum size) gives 127 clusters / 32.09% noise with ARI 0.184 against the selected DBSCAN labels, i.e. a variable-density method gives a materially different partition.

## 4. Sensitivity and duplicate-coordinate behaviour

- Re-running the same eps/min_samples **with** the suspected fallback pins gives 85 clusters and 66.35% noise (without: 76 and 70.43%); the single most-reused pin holds 43 pothole reports at one coordinate, which would otherwise appear as a dense 'hotspot' that is only a default map location.
- 365 pothole reports share an exact coordinate with another pothole report; repeated reports at one place are kept (they can be genuine repeat complaints) and are distinct from duplicated records (2 surrogate-key duplicates among pothole rows).
- The fallback-pin threshold (multiplicity >= 8) is a heuristic; see `fallback_pin_sensitivity_pothole_rows` in `reports/data_feasibility.json` for other cut-offs.

## 5. Monthly activity and normalisation

| Year | Pothole reports (analysed set) | All complaints | Pothole share |
|---|---|---|---|
| 2019 | 1232 | 6727 | 18.3% |
| 2020 | 465 | 4094 | 11.4% |
| 2021 | 199 | 2447 | 8.1% |
| 2022 | 86 | 1381 | 6.2% |

- City-wide observed trend (monthly Kendall tau): **Decreasing** (tau=-0.565, q=1.1e-07); the pothole *share* of all complaints also shows tau=-0.462.
- Latest 3 months of the dataset: 17.0 reports/month vs 48.3/month over the earlier months (-65%). This is platform-wide decline in portal use, so cluster-level 'recent activity' mostly shows the same decline; read cluster values against this city baseline.
- Normalisation: pothole reports / all complaints for the same unit and period (clusters: all complaints inside the cluster footprint). It partly controls for portal activity but not for population, awareness or adoption differences.
- Cluster observed trends (Kendall tau, BH-adjusted q<0.05, >= 10 reports and >= 12 months): {'Insufficient data': 63, 'Decreasing': 12, 'Stable': 1}. Most clusters have too few reports for any trend claim. These are observed trends, not established changes in road condition.

## 6. Recurring areas (fixed units)

- Unit: BBMP 2015 wards (polygon-assigned). 43 eligible months (>= 24 required: persistence is supported).
- Active month: unit-month is active when pothole reports >= T, where T is the smallest count with P(Poisson(rate x unit area) >= T) <= 0.05 (null: reports spread uniformly at the city-wide rate). Resulting per-ward thresholds: {'1': 33, '2': 127, '3': 29, '4': 5, '5': 4} (count of wards per threshold).
- Persistent ward: persistent when active months >= smallest k with P(Binomial(eligible_months, p0) >= k) <= 0.01. **26 of 198 wards** qualify. Top by reports: Bellanduru (157 reports, 13/43 active months), Begur (100 reports, 12/43 active months), Horamavu (97 reports, 9/43 active months), Varthuru (75 reports, 8/43 active months), Thanisandra (67 reports, 12/43 active months).
- Caveat: the null ignores population and adoption; 89% of the persistent wards' pothole reports fall in 2019-2020 (portal use fell afterwards), so persistence mostly describes the earlier period. Clusters report only the descriptive active-month share; no persistence test is applied to clusters because they are selected for density (testing them against a uniform null would be circular).

## 7. Cross-check against BBMP Fix My Street (separate source, May-June 2022)

- 16,534 Fix My Street pothole records inside the boundary (dates 2022-04-13 to 2022-06-18) against 37 iCMyC pothole reports in the same months: iCMyC captures a tiny and probably unrepresentative slice of 2022 reporting.
- Ward-level Spearman correlation of counts: 0.209 (weak; iCMyC n is tiny). Top-20-ward overlap: 2.
- Fix My Street density inside iCMyC cluster footprints: 47.1/km2 vs 23.0/km2 elsewhere (ratio 2.05). Independent complaint density is higher where iCMyC clusters sit, which supports the clusters as places of repeated *reporting*, subject to the same reporting biases.

## 8. Limitations

- Complaints are not potholes: no physical measurement, no severity, no ground truth. Complaint density is not road-condition severity.
- Reporting bias: uneven portal adoption, awareness, civic engagement and population across wards.
- Historical, non-real-time data that ends 2022-07-31; reporting volume collapses over time, confounding trends.
- Coordinates: locality-level and default pins exist; a rule-based exclusion is used and is itself a heuristic.
- City boundary = BBMP 2015 ward union; reports outside it (mostly source ward 199 'Other') are excluded from the analysis.
- DBSCAN uses one global density threshold: sparse periphery is under-detected and dense cores can merge.
- No request IDs in the source; repeat reports cannot be tied to unique complainants or unique potholes.
- Parameter choice is a judgment among few passing configurations; cluster counts at nearby settings differ materially.
