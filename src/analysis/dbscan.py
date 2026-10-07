"""DBSCAN on geographic points using haversine distance (radians); eps is
exposed in metres."""
from __future__ import annotations

import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint
from sklearn.cluster import DBSCAN
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.neighbors import NearestNeighbors

from src.geo.distance import centroid, haversine_m, meters_to_radians, radius_m, to_latlon, to_xy

NOISE = -1
BOUNDARY_BUFFER_M = 50


def run_dbscan(lat, lon, eps_meters: float, min_samples: int) -> np.ndarray:
    if eps_meters <= 0:
        raise ValueError("eps_meters must be > 0")
    if min_samples < 1:
        raise ValueError("min_samples must be >= 1")
    coords = np.radians(np.column_stack([np.asarray(lat, float), np.asarray(lon, float)]))
    model = DBSCAN(eps=meters_to_radians(eps_meters), min_samples=min_samples,
                   metric="haversine", algorithm="ball_tree")
    return model.fit_predict(coords)


def k_distances(lat, lon, k: int) -> np.ndarray:
    """Sorted distance (m) from each point to its k-th nearest OTHER point.
    A point's own entry is index 0, so k+1 neighbours are queried (matching
    DBSCAN's min_samples, which counts the point itself)."""
    coords = np.radians(np.column_stack([lat, lon]))
    nn = NearestNeighbors(n_neighbors=k, metric="haversine", algorithm="ball_tree").fit(coords)
    dist, _ = nn.kneighbors(coords)
    return np.sort(dist[:, -1] * 6_371_008.8)


def knee_index(sorted_vals: np.ndarray) -> int:
    """Kneedle-style heuristic: point of max distance below the chord of the
    sorted curve. A heuristic, not an optimum."""
    n = len(sorted_vals)
    x = np.linspace(0, 1, n)
    y = (sorted_vals - sorted_vals[0]) / max(sorted_vals[-1] - sorted_vals[0], 1e-12)
    return int(np.argmax(x - y))


def sweep_row(lat, lon, labels, eps, min_samples, with_silhouette=False) -> dict:
    n = len(labels)
    clustered = labels != NOISE
    sizes = pd.Series(labels[clustered]).value_counts() if clustered.any() else pd.Series(dtype=int)
    n_clustered = int(clustered.sum())
    row = {
        "eps_meters": eps, "min_samples": min_samples, "points": n,
        "cluster_count": int(len(sizes)), "clustered_reports": n_clustered,
        "noise_count": int(n - n_clustered), "noise_percentage": round(100 * (n - n_clustered) / n, 2),
        "largest_cluster_size": int(sizes.max()) if len(sizes) else 0,
        "largest_cluster_share": round(float(sizes.max() / n_clustered), 4) if n_clustered else 0.0,
        "median_cluster_size": float(sizes.median()) if len(sizes) else 0.0,
        "max_cluster_radius_m": 0.0, "single_coordinate_cluster_share": 0.0,
    }
    if len(sizes):
        lat, lon = np.asarray(lat), np.asarray(lon)
        mr, single = 0.0, 0
        for cid in sizes.index:
            m = labels == cid
            c = centroid(lat[m], lon[m])
            mr = max(mr, radius_m(lat[m], lon[m], *c))
            single += int(pd.Series(list(zip(lat[m], lon[m]))).value_counts().iloc[0] / m.sum() >= 0.9)
        row["max_cluster_radius_m"] = round(mr, 1)
        row["single_coordinate_cluster_share"] = round(single / len(sizes), 3)
    # supplementary only: never used for selection
    row["silhouette_supplementary"] = None
    if with_silhouette and len(sizes) >= 2 and n_clustered > len(sizes):
        x, y = to_xy(np.asarray(lat)[clustered], np.asarray(lon)[clustered])
        try:
            row["silhouette_supplementary"] = round(float(silhouette_score(np.column_stack([x, y]), labels[clustered])), 3)
        except ValueError:
            pass
    return row


def sanity_warnings(row: dict) -> list[str]:
    row = {**row, 'eps_meters': f"{row['eps_meters']:g}", 'min_samples': int(row['min_samples'])}
    w = []
    if row["cluster_count"] == 0 or row["noise_percentage"] > 85:
        w.append(f"WARNING: eps={row['eps_meters']} m, min_samples={row['min_samples']} labels "
                 f"{row['noise_percentage']}% of reports as noise (almost everything is noise).")
    if row["cluster_count"] and row["largest_cluster_share"] > 0.5:
        w.append(f"WARNING: eps={row['eps_meters']} m, min_samples={row['min_samples']} creates one cluster "
                 f"containing {round(100 * row['largest_cluster_share'])}% of clustered reports. Review parameter choice.")
    if row["cluster_count"] and row["cluster_count"] <= 2 and row["noise_percentage"] < 10:
        w.append(f"WARNING: eps={row['eps_meters']} m, min_samples={row['min_samples']} merges almost every report "
                 f"into {row['cluster_count']} cluster(s).")
    if row["max_cluster_radius_m"] > 4000:
        w.append(f"WARNING: largest cluster radius is {row['max_cluster_radius_m']:.0f} m (geographically huge).")
    if row["single_coordinate_cluster_share"] > 0.25:
        w.append(f"WARNING: eps={row['eps_meters']} m, min_samples={row['min_samples']}: "
                 f"{round(100 * row['single_coordinate_cluster_share'])}% of clusters consist almost entirely of reports at one "
                 f"repeated coordinate (repeated reports at one pin, not a spatial spread).")
    return w


def parameter_sweep(lat, lon, eps_list, min_samples_list, with_silhouette=True):
    """Return (sweep DataFrame, {(eps, ms): labels})."""
    rows, labs = [], {}
    for ms in min_samples_list:
        for eps in eps_list:
            lab = run_dbscan(lat, lon, eps, ms)
            labs[(eps, ms)] = lab
            rows.append(sweep_row(lat, lon, lab, eps, ms, with_silhouette))
    df = pd.DataFrame(rows)
    # stability: ARI against the next-larger and next-smaller eps at the same min_samples
    stab = []
    for ms in min_samples_list:
        for i, eps in enumerate(eps_list):
            nb = [eps_list[j] for j in (i - 1, i + 1) if 0 <= j < len(eps_list)]
            aris = [adjusted_rand_score(labs[(eps, ms)], labs[(e2, ms)]) for e2 in nb]
            stab.append({"eps_meters": eps, "min_samples": ms, "stability_ari": round(float(np.mean(aris)), 3)})
    df = df.merge(pd.DataFrame(stab), on=["eps_meters", "min_samples"])
    df["warnings"] = df.apply(lambda r: " | ".join(sanity_warnings(r.to_dict())), axis=1)
    return df, labs


def cluster_table(df_points: pd.DataFrame, labels: np.ndarray, eps_meters: float) -> pd.DataFrame:
    """Per-cluster stats. df_points needs latitude, longitude, created_at."""
    lat, lon = df_points["latitude"].to_numpy(), df_points["longitude"].to_numpy()
    rows = []
    for cid in sorted(set(labels) - {NOISE}):
        m = labels == cid
        c_lat, c_lon = centroid(lat[m], lon[m])
        x, y = to_xy(lat[m], lon[m])
        hull = MultiPoint(np.column_stack([x, y])).convex_hull
        floor_area = np.pi * (eps_meters / 2) ** 2
        area = max(hull.area, floor_area)
        # Visualisation boundary: hull buffered by 50 m so published polygon vertices
        # are not exact complaint coordinates. It is NOT a pothole area.
        bnd = hull.buffer(BOUNDARY_BUFFER_M)
        bx, by = bnd.exterior.coords.xy
        blat, blon = to_latlon(np.array(bx), np.array(by))
        hull_ll = [[round(float(a), 5), round(float(b), 5)] for a, b in zip(blon, blat)]
        t = df_points["created_at"][m]
        rows.append({
            "cluster_id": int(cid), "report_count": int(m.sum()),
            "distinct_coordinates": int(pd.Series(list(zip(lat[m], lon[m]))).nunique()),
            "single_coordinate_cluster": bool(pd.Series(list(zip(lat[m], lon[m]))).value_counts().iloc[0] / m.sum() >= 0.9),
            "centroid_latitude": c_lat, "centroid_longitude": c_lon,
            "approx_radius_meters": round(radius_m(lat[m], lon[m], c_lat, c_lon), 1),
            "date_min": t.min().isoformat(), "date_max": t.max().isoformat(),
            "bbox_min_lat": float(lat[m].min()), "bbox_min_lon": float(lon[m].min()),
            "bbox_max_lat": float(lat[m].max()), "bbox_max_lon": float(lon[m].max()),
            "boundary_area_km2": round(area / 1e6, 5),
            "density_reports_per_km2": round(m.sum() / (area / 1e6), 1),
            "boundary": hull_ll,
        })
    return pd.DataFrame(rows)
