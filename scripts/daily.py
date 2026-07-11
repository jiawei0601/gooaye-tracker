#!/usr/bin/env python3
"""每日排程主流程：抓 feed → 分析 pending（新集數＋回填配額）→ 彙整 → 儀表板 → 推播。

回填靜音規則：只推播發布日在 5 天內的集數，歷史回填不轟炸 Telegram。
用法：python scripts/daily.py [--limit 4]
"""
import argparse
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from common import ANALYSES

HERE = Path(__file__).parent
PY = sys.executable


def run(script, *args):
    r = subprocess.run([PY, str(HERE / script), *args], cwd=HERE.parent)
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", default="4")
    args = ap.parse_args()

    if run("fetch_feed.py"):
        return 1
    run("analyze.py", "--limit", args.limit)  # 個別集失敗不中斷全流程
    run("aggregate.py")
    run("build_dashboard.py")

    marker = ANALYSES / ".last_processed.json"
    if marker.exists():
        processed = json.loads(marker.read_text(encoding="utf-8"))
        cutoff = (date.today() - timedelta(days=5)).isoformat()
        fresh = [k for k in processed
                 if (ANALYSES / f"{k}.json").exists()
                 and json.loads((ANALYSES / f"{k}.json").read_text(encoding="utf-8"))["pubdate"] >= cutoff]
        if fresh:
            run("notify.py", *fresh)
        marker.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
