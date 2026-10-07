# DATASET FEASIBILITY (data gate)

Gate rule: usable pothole points >= 500 and months covered >= 24.
**Result: PASSED.** Full measurements: `reports/data_feasibility.json`.

| Measurement | Value |
|---|---|
| Rows / columns | 16,071 / 17 |
| Columns | `created_at`, `ward_id`, `title`, `description`, `sub_category_id`, `civic_agency_id`, `location`, `address`, `latitude`, `longitude`, `ward_title`, `category_id`, `category_title`, `sub_category_title`, `civic_agency_title`, `complaint_status_title`, `comment_count` |
| File encoding | cp1252 (not UTF-8) |
| Date range | 2019-01-01T06:33:00+05:30 to 2022-07-31T20:08:00+05:30 (43 calendar months with data) |
| Missing timestamps | 0 |
| Missing coordinates | 0 (0.0%) |
| Rows inside Bengaluru boundary | 15,411 (95.89%) |
| Pothole rows (taxonomy) | 2,252 |
| ... with valid coordinates | 2,252 |
| ... inside boundary | 2,095 |
| ... after excluding suspected fallback pins | 1,982 |
| Months covered by usable pothole points | 43 |
| Duplicate request IDs | none available (source has no identifier) |
| Duplicate surrogate keys (all / pothole) | 47 / 2 |
| Exact duplicate raw rows (all columns) | 33 |
| Unique coordinates (all / pothole) | 12,971 / 2,015 |

## Pothole filter (taxonomy-based, no keyword matching)

Included (`sub_category_id`): 66 *Fixing/Reparing Potholes* (category *Mobility - Roads, Footpaths and Infrastructure*) and
594 *Repair of Potholes on Roads* (category *PWD*). The filter aborts if these ids stop carrying these titles.
Excluded: every other category, including *Tarring Or Asphalting Of Existing Road* (resurfacing requests) and complaint titles that merely mention
"pothole" in other sub-categories. Frequency table: `reports/category_distribution.csv`.

## Verdict

1,982 usable pothole observations over 43 months is enough for DBSCAN, but modest: the point set is sparse
(median nearest-neighbour distance a few hundred metres), so clusters are small and most reports are noise. Platform usage also declines
steeply over the period. These are limitations of the data, documented in `reports/analysis_report.md`.
