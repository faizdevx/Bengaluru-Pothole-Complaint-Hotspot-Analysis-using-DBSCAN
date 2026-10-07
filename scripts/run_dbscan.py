"""Run k-distance analysis, the DBSCAN parameter sweep and the final clustering.
Optional: --eps METRES --min-samples N to override the documented selection."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.analysis.run import run_dbscan_stage  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--eps", type=float)
    ap.add_argument("--min-samples", type=int)
    a = ap.parse_args()
    print(run_dbscan_stage(a.eps, a.min_samples))
