#!/usr/bin/env python3
"""從 whatmkreallysaid.com 同步股癌全集逐字稿（粉絲站，站方以 transcripts.json.br
單檔打包供前端搜尋，抓一次 = 全站，比逐頁爬有禮貌）。

用法：
  python scripts/fetch_web_transcripts.py          # 增量：無新集數就不下載大包
  python scripts/fetch_web_transcripts.py --force  # 全量重抓覆蓋

輸出：data/transcripts_web/EPnnn.md（⚠️ 版權考量僅存本機，已在 .gitignore 排除，
絕不能加入版控——同 data/transcripts/ 的既有雷區規則）。
需要：pip install brotli
"""
import argparse
import json
import re
import sys
import urllib.request

from common import DATA

SITE = "https://whatmkreallysaid.com"
OUT = DATA / "transcripts_web"
UA = {"User-Agent": "gooaye-tracker-personal-sync/1.0 (contact: local use only)"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    try:
        import brotli
    except ImportError:
        print("❌ 缺 brotli：python -m pip install brotli")
        return 1

    OUT.mkdir(exist_ok=True)
    have = {int(m.group(1)) for p in OUT.glob("EP*.md")
            if (m := re.match(r"EP(\d+)", p.stem))}

    # 先抓輕量索引，判斷有沒有新集數（避免每晚白抓 10MB 大包）
    index = json.loads(get(f"{SITE}/episodes.json"))
    site_nums = {e["number"] for e in index}
    new = site_nums - have
    if not new and not args.force:
        print(f"無新集數（本地 {len(have)}／站上 {len(site_nums)}），跳過")
        return 0

    print(f"站上 {len(site_nums)} 集、本地 {len(have)} 集、待抓 {len(new) if not args.force else len(site_nums)} 集，下載打包檔 ...", flush=True)
    pack = json.loads(brotli.decompress(get(f"{SITE}/transcripts.json.br")))

    written = 0
    for e in pack:
        n = e.get("n")
        tx = e.get("tx", "")
        if not n or not tx:
            continue
        if n in have and not args.force:
            continue
        head = (f"# EP{n} ｜ {e.get('t', '')} — {e.get('d', '')}\n"
                f"# 來源：{SITE}（粉絲逐字稿站，僅本機使用）\n\n")
        (OUT / f"EP{n}.md").write_text(head + tx, encoding="utf-8")
        written += 1
    print(f"✅ 寫入 {written} 集 → {OUT}（總計 {len(list(OUT.glob('EP*.md')))} 集）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
