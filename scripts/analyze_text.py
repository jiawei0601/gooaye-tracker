#!/usr/bin/env python3
"""全歷史文字回填：用 whatmkreallysaid.com 逐字稿（data/external/wmrs/）＋ NIM GLM
分析 EP1-518（skipped 集數），輸出與 analyze.py 同構的 data/analyses/EPxxx.json。

免 Gemini 額度、無日限。可中斷續跑（已有分析檔的集數自動跳過）。

用法：
  python scripts/analyze_text.py               # 全部 skipped 由新到舊
  python scripts/analyze_text.py --limit 20    # 限量
  python scripts/analyze_text.py --ep EP100    # 指定單集
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

from analyze import PROMPT, parse_json
from common import ANALYSES, DATA, load_episodes, save_episodes

NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODEL = "z-ai/glm-5.2"  # 免額度；與 serenity-tracker synthesize 同管道
WMRS = DATA / "external" / "wmrs" / "transcripts.json"


def text_prompt(key, ep):
    """analyze.py 的 PROMPT 去掉 transcript 欄位（輸入已是文字，不需再產逐字稿）。"""
    p = PROMPT.format(key=key, title=ep["title"], pubdate=ep["pubdate"])
    p = p.replace("的完整音檔。請仔細聽完後輸出", "的完整逐字稿（見文末）。請讀完後輸出")
    p = p.replace(' "transcript": [{"t":"mm:ss 段落起始時間","text":"該段逐字稿，口語照實記錄"}]\n', "")
    p = p.replace("transcript 需涵蓋全集、不可省略跳段，每段約 30-60 秒內容。\n", "")
    return p


def nim_generate(prompt, transcript_text):
    body = {
        "model": NIM_MODEL,
        "temperature": 0.2,
        "max_tokens": 8192,
        "messages": [{"role": "user",
                      "content": f"{prompt}\n\n=== 逐字稿全文 ===\n{transcript_text}"}],
    }
    req = urllib.request.Request(
        NIM_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {os.environ['NVIDIA_NIM_API_KEY']}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.load(r)
    return resp["choices"][0]["message"]["content"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10**6)
    ap.add_argument("--ep")
    args = ap.parse_args()

    if not os.environ.get("NVIDIA_NIM_API_KEY"):
        print("❌ 缺 NVIDIA_NIM_API_KEY")
        return 1

    wmrs = {e["n"]: e for e in json.loads(WMRS.read_text(encoding="utf-8"))}
    eps = load_episodes()
    if args.ep:
        todo = [args.ep] if args.ep in eps else []
    else:
        todo = sorted((k for k, e in eps.items()
                       if e["status"] == "skipped" and not (ANALYSES / f"{k}.json").exists()),
                      key=lambda k: eps[k]["pubdate"], reverse=True)[: args.limit]
    print(f"待文字分析 {len(todo)} 集", flush=True)

    fails = 0
    done = 0
    for key in todo:
        m = re.match(r"EP(\d+)", key)
        src = wmrs.get(int(m.group(1))) if m else None
        if not src or not src.get("tx"):
            print(f"{key}: ⚠️ 外部逐字稿缺此集，跳過", flush=True)
            continue
        ep = eps[key]
        try:
            result = parse_json(nim_generate(text_prompt(key, ep), src["tx"]))
            result.pop("transcript", None)
            result.update(ep_key=key, title=ep["title"], pubdate=ep["pubdate"],
                          duration_s=ep["duration_s"],
                          analysis_source="text/whatmkreallysaid")
            (ANALYSES / f"{key}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            eps[key]["status"] = "done"
            eps[key]["via"] = "wmrs-text"
            save_episodes(eps)
            done += 1
            fails = 0
            print(f"{key}: ✅ {len(result.get('tickers', []))} 檔標的（{done}/{len(todo)}）",
                  flush=True)
        except Exception as e:
            fails += 1
            print(f"{key}: ❌ {e}", flush=True)
            if fails >= 5:
                print("連續失敗 5 次，停批（NIM 可能異常）", flush=True)
                break
            time.sleep(30)
        time.sleep(2)
    print(f"完成 {done} 集", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
