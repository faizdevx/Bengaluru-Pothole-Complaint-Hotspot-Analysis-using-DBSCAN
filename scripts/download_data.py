"""Download the public source files: python scripts/download_data.py [--force]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.ingestion.download import download_all  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    for m in download_all(ap.parse_args().force):
        print(f"{m['key']}: {m['status']}", {k: m[k] for k in ("file_size", "sha256", "retrieved_at") if k in m})
