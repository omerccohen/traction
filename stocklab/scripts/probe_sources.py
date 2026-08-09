#!/usr/bin/env python3
"""Live-probe the news/sentiment/attention data sources and print a reachability
table. Every row is a real HTTP request from THIS environment — no assumptions.

The shared-egress IP gets rate-limited unpredictably, so "reachable" can flip
week to week; this script is the ground truth at run time. Backs the claims in
docs/RESEARCH_DATA_SOURCES.md.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
SEC_UA = "stocklab research omerccohen@gmail.com"

# (label, url, extra_headers, validator) — validator(text) -> short content note
SOURCES = [
    ("SEC_EDGAR_submissions",
     "https://data.sec.gov/submissions/CIK0000320193.json", SEC_UA,
     lambda t: f"forms={len(json.loads(t).get('filings',{}).get('recent',{}).get('form',[]))}"),
    ("SEC_EDGAR_fulltext",
     "https://efts.sec.gov/LATEST/search-index?q=%22data+center%22&forms=8-K", SEC_UA,
     lambda t: "json ok" if t.strip().startswith("{") else "non-json"),
    ("Wikipedia_pageviews",
     "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
     "en.wikipedia/all-access/all-agents/Nvidia/daily/20260701/20260808", UA,
     lambda t: f"days={len(json.loads(t).get('items',[]))}"),
    ("FINRA_RegSHO",
     "https://cdn.finra.org/equity/regsho/daily/CNMSshvol20260806.txt", UA,
     lambda t: f"rows={len(t.splitlines())}"),
    ("StockTwits_symbol",
     "https://api.stocktwits.com/api/2/streams/symbol/NVDA.json", UA,
     lambda t: f"msgs={len(json.loads(t).get('messages',[]))}"),
    ("GoogleNews_RSS",
     "https://news.google.com/rss/search?q=Nvidia+when:7d&hl=en-US&gl=US&ceid=US:en", UA,
     lambda t: f"items={t.count('<item>')}"),
    ("GDELT_doc",
     "https://api.gdeltproject.org/api/v2/doc/doc?query=datacenter&mode=timelinevol&format=json&timespan=7d", UA,
     lambda t: "json ok" if t.strip().startswith("{") else "non-json (flaky)"),
    ("Reddit_json",
     "https://www.reddit.com/r/stocks/hot.json?limit=5", UA, None),
    ("Yahoo_RSS",
     "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA", UA,
     lambda t: f"items={t.count('<item>')}"),
    ("GoogleTrends",
     "https://trends.google.com/trends/api/explore", UA, None),
]


def probe(url: str, ua: str) -> tuple[str, str]:
    """Return (http_code, body_or_empty). Uses curl — urllib times out on this
    environment's proxy; curl carries the CA bundle it expects."""
    try:
        out = subprocess.run(
            ["curl", "-sS", "--http1.1", "-A", ua,
             "-w", "\n__CODE__%{http_code}", "--max-time", "25", url],
            capture_output=True, text=True, timeout=35).stdout
        body, _, code = out.rpartition("__CODE__")
        return code.strip() or "???", body
    except Exception as e:
        return f"ERR:{type(e).__name__}", ""


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    print(f"# Source reachability — live probe {stamp}\n")
    print(f"{'source':24s} {'code':6s} content")
    print("-" * 60)
    for label, url, ua, validator in SOURCES:
        code, body = probe(url, ua)
        note = ""
        if code == "200" and validator and body:
            try:
                note = validator(body)
            except Exception:
                note = "200 but unparseable"
        elif code != "200":
            note = "BLOCKED/flaky"
        print(f"{label:24s} {code:6s} {note}")


if __name__ == "__main__":
    main()
