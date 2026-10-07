# DATASET

## Primary dataset

| Field | Value |
|---|---|
| Dataset name | I Change My City Complaints Log - 2019 - 2022 |
| Publisher / source | Janaagraha (I Change My City, "iCMyC") |
| Host | OpenCity (data.opencity.in) - a redistributor, **not** the originating civic authority |
| OpenCity dataset | `i-change-my-city-data` |
| Resource identifier | `a60abf5c-3a15-4967-af32-c3074248580f` |
| License | Creative Commons Attribution Share-Alike (CC BY-SA) |
| Retrieval date (UTC) | 2026-10-07T12:36:07+00:00 |
| File size / SHA-256 | 8377752 bytes / `d951dbb484532421801f6cbd7550edaa6f9ab143da7c4d0e835ba574e4e6d5ac` |
| Original date range (data as measured) | 2019-01-01T06:33:00+05:30 to 2022-07-31T20:08:00+05:30 |
| Actual row count | 16,071 |
| Actual pothole row count | 2,252 |
| Actual valid-coordinate count | 16,071 all rows (100.0%); 2,252 pothole rows |
| Pothole rows inside Bengaluru boundary | 2,095 |
| Pothole rows used by DBSCAN | 1,982 (suspected fallback pins excluded: 113) |

**The primary dataset is Janaagraha / I Change My City civic-tech complaint data, not a direct BBMP real-time API.**
OpenCity is only the host. It is a historical file, not a live feed.

Attribution (CC BY-SA): *Janaagraha, "I Change My City Complaints Log - 2019 - 2022", via OpenCity
(https://data.opencity.in/dataset/i-change-my-city-data), licensed under CC BY-SA.*
Derived outputs in this repository (aggregates, cluster summaries) are shared under the same share-alike terms.

## Latitude / longitude quality (measured)

- Missing coordinates: 0 (0.0%).
- Coordinate extent (all rows): lat 12.7123-13.1828, lon 77.4309-77.8094.
- Pothole rows with <=3 decimals (coarse): 0 (0.0%).
- Pothole rows outside the BBMP ward union: 157 (6.972%).
- Pothole rows whose source `ward_id` disagrees with the polygon ward (inside boundary): 98 (4.352%).
- Exact coordinates shared with another pothole report: 365 rows;
  within 10 m of another pothole report: 484 rows.
- **Suspected default / geocoder-fallback pins.** Many coordinates are reused by dozens of complaints of unrelated categories over
  months or years (the single most-reused coordinate carries 81 complaints, 43 of them pothole reports; see `reports/duplicate_coordinate_analysis.csv`).
  Rule used: a coordinate shared by >= 8 complaints of any category is flagged. 113 pothole rows are affected and are excluded from DBSCAN
  (a sensitivity run that includes them is recorded in the analysis report).

## Timestamps

Two formats occur (`1-1-2019 06:33` and `7/31/2022 14:03`); both are month-first (zero chronological inversions in file order vs 39 under day-first).
Naive local times are treated as Asia/Kolkata. Missing timestamps: 0.
The file ends 2022-07-31, i.e. it covers 2019 to July 2022, not the whole of 2022.
Yearly counts: 2019: 1403 pothole / 7383 all; 2020: 515 pothole / 4492 all; 2021: 230 pothole / 2645 all; 2022: 104 pothole / 1551 all. Reporting volume falls sharply over time.

## Known limitations

- Not live, not complete: user-submitted reports on one civic-tech portal; no physical road-condition ground truth.
- No request identifier exists in the source (`request_id` is a surrogate content hash).
- Strong decline in platform usage (see yearly counts) confounds any trend or "recent activity" statistic.
- Locality-level geocodes and repeated pins reduce positional precision (see above).
- Free-text fields (`title`, `description`, `location`, `address`) are dropped during preprocessing and never stored or published.

## Boundary source (for assigning wards and defining "inside Bengaluru")

| Field | Value |
|---|---|
| boundary_source | BBMP Ward Map - 2015 (198 wards), OpenCity bbmp-ward-information |
| boundary_vintage | 2015 delimitation (198 wards; in force through the data period) |
| boundary_type | Union of official ward polygons (administrative; not an approximation) |
| License | Not specified in the OpenCity metadata (`license_title: None`) |
| SHA-256 | `44c721814b0bcf9faab48a09f621cb1a27cf5fc081c49d5dc1ecba0c85bee4cc` |

15,411 of 16,071 rows (95.89%) fall inside it. Most of the rest carry the source's own ward 199 "Other" label.

## Secondary dataset (kept separate)

BBMP Fix My Street Data - May and June 2022 (OpenCity dataset `bbmp-fix-my-street-data`, resource `d1d4a437-95ee-4327-9154-f9a8933b2110`, licence Other (Public Domain)).
Retrieved 2026-10-07T12:36:15+00:00, SHA-256 `7c91b31b7bf4aa882f612c51f1ffd15ae2dee25ba3f32e67457024486ec421e6`. Its KML contains complainant names and phone numbers; they are discarded while
parsing and never stored. It is **not merged** with the primary data: it is used only for validation and triangulation (see the analysis report).
