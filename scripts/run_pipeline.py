"""Run the complete pipeline: python scripts/run_pipeline.py [--skip-download]"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.analysis.run import run_dbscan_stage  # noqa: E402
from src.analysis.stage import run_temporal_stage  # noqa: E402
from src.data.pipeline import run_preprocess  # noqa: E402
from src.ingestion.download import download_all  # noqa: E402
from src.reporting.docs import write_analysis_report, write_dataset_docs  # noqa: E402
from src.reporting.exports import export_cluster_files  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true", help="use files already in data/raw")
    a = ap.parse_args()
    if not a.skip_download:
        for m in download_all():
            print("download:", m["key"], m["status"])
    gate = run_preprocess()
    write_dataset_docs()
    if not gate["gate_passed"]:
        print("DATA GATE FAILED - see DATASET_FEASIBILITY.md; analysis not run.")
        sys.exit(2)
    print("dbscan:", run_dbscan_stage())
    print("temporal:", run_temporal_stage())
    export_cluster_files()
    write_analysis_report()
    print("pipeline complete")
