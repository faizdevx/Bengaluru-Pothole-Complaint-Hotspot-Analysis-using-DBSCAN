"""Monthly spatial analysis, persistence, recent activity and trends."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.analysis.stage import run_temporal_stage  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(run_temporal_stage())
