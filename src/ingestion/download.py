"""Reproducible downloader for the public OpenCity resources.

Only the public download URLs listed in src.config.SOURCES are used. Each
download records retrieved_at, file size, SHA-256 and the source identifier.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import requests

from src.config import DATA_META, DATA_RAW, SOURCES


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_source(key: str, force: bool = False) -> dict:
    src = SOURCES[key]
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    DATA_META.mkdir(parents=True, exist_ok=True)
    dest = DATA_RAW / src["file"]
    meta_path = DATA_META / f"{key}.json"
    if dest.exists() and meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text())
        if meta.get("sha256") == sha256_of(dest):
            meta["status"] = "cached"
            return meta
    resp = requests.get(src["url"], timeout=300)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    meta = {
        "key": key,
        "label": src["label"],
        "source_identifier": f"{src['dataset']}/{src['resource_id']}",
        "publisher": src["publisher"],
        "host": src["host"],
        "license": src["license"],
        "url": src["url"],
        "file": src["file"],
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_size": dest.stat().st_size,
        "sha256": sha256_of(dest),
        "http_status": resp.status_code,
        "status": "downloaded",
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def download_all(force: bool = False) -> list[dict]:
    results = []
    for key, src in SOURCES.items():
        try:
            results.append(download_source(key, force))
        except Exception as exc:  # optional sources may fail without stopping the pipeline
            if src["required"]:
                raise
            results.append({"key": key, "status": "failed", "error": str(exc)})
    return results
