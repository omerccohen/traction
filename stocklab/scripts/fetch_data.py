#!/usr/bin/env python3
"""Fetch the bundled dataset (public S&P 500 daily OHLCV, 2013-2018).

The repo already ships data_cache/all_stocks_5yr.csv.gz; this script exists to
re-fetch it (or fetch it in a fresh clone without LFS-style artifacts).

Sources tried in order:
  1. plotly/datasets GitHub mirror (raw.githubusercontent.com)
"""
from __future__ import annotations

import gzip
import shutil
import sys
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/plotly/datasets/master/all_stocks_5yr.csv"
DEST = Path(__file__).resolve().parents[1] / "data_cache" / "all_stocks_5yr.csv.gz"


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        print(f"already present: {DEST}")
        return 0
    tmp = DEST.with_suffix(".tmp")
    print(f"fetching {URL} ...")
    with urllib.request.urlopen(URL, timeout=120) as r, open(tmp, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb") as gz:
            shutil.copyfileobj(r, gz)
    tmp.rename(DEST)
    print(f"saved -> {DEST} ({DEST.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
