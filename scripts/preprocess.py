"""Validate, normalise, filter and quality-check the data: python scripts/preprocess.py"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.data.pipeline import run_preprocess  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    gate = run_preprocess()
    print("gate_passed:", gate["gate_passed"], "| usable pothole points:", gate["pothole"]["usable_for_dbscan"])
    sys.exit(0 if gate["gate_passed"] else 2)
