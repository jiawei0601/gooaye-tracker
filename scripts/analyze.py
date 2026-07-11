#!/usr/bin/env python3
"""下載音檔 → Gemini 2.5 Flash 音訊理解 → data/analyses/EPxxx.json。

用法：
  python scripts/analyze.py            # 處理所有 pending（新→舊），預設上限 6 集/次
  python scripts/analyze.py --limit 30 # 一次補完回填佇列（注意免費層 TPM，逐集間隔 30s）
  python scripts/analyze.py --ep EP678 # 指定單集重跑
"""
import argparse
import json
import re
import sys
import time
import urllib.request

from common import ANALYSES, AUDIO, gemini_key, load_episodes, save_episodes

MODEL = "gemini-2.5-flash"
PAUSE_S = 30  # 免費層 250k TPM，一集約 10 萬 token，逐集間隔避免 429

PROMPT = """你是台股/美股 podcast 內容分析師。這是台灣 podcast《股癌》(主持人謝孟恭) 第 {key} 集
「{title}」({pubdate}) 的完整音檔。請仔細聽完後輸出 JSON（繁體中文），格式：
{{
 "summary": "全集摘要 150-250 字，涵蓋總經判斷與主要論點",
 "topics": ["本集討論主題，3-8 條"],
 "market_view": "主持人對大盤/總經的當下看法一句話（沒有就填 null）",
 "industries": [{{"name":"產業名(如 半導體/AI伺服器/航運)","stance":"看多|看空|中性|觀察","view":"看法摘要一句話"}}],
 "tickers": [{{"symbol":"股票代號(台股用數字如 2330，美股用代號如 NVDA；聽不出代號就用公司名)",
              "name":"公司名","market":"TW|US|other","stance":"看多|看空|中性|觀察|持有中|已出場",
              "argument":"主持人對它的論點一句話"}}],
 "quotes": ["值得記錄的觀點或提醒，1-3 條"]
}}
規則：只記錄主持人明確討論的產業與個股，聽眾問答提到但主持人沒表態的標記 stance=觀察。
不要腦補沒提到的標的。只輸出 JSON，不要 markdown 圍欄。"""


def parse_json(text):
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def download(url, dest):
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "gooaye-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def analyze_one(client, key, ep):
    from google.genai import types

    mp3 = AUDIO / f"{key}.mp3"
    print(f"{key}: 下載音檔 ...", flush=True)
    download(ep["audio_url"], mp3)
    print(f"{key}: 上傳 Gemini ({mp3.stat().st_size >> 20}MB) ...", flush=True)
    f = client.files.upload(file=str(mp3))
    try:
        while f.state.name == "PROCESSING":
            time.sleep(5)
            f = client.files.get(name=f.name)
        if f.state.name != "ACTIVE":
            raise RuntimeError(f"file state={f.state.name}")
        print(f"{key}: 分析中 ...", flush=True)
        resp = client.models.generate_content(
            model=MODEL,
            contents=[f, PROMPT.format(key=key, title=ep["title"], pubdate=ep["pubdate"])],
            config=types.GenerateContentConfig(temperature=0.2),
        )
        result = parse_json(resp.text)
    finally:
        try:
            client.files.delete(name=f.name)
        except Exception:
            pass
    result.update(ep_key=key, title=ep["title"], pubdate=ep["pubdate"],
                  duration_s=ep["duration_s"])
    (ANALYSES / f"{key}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    mp3.unlink(missing_ok=True)  # 音檔用完即刪，省磁碟
    print(f"{key}: ✅ {len(result.get('tickers', []))} 檔標的、"
          f"{len(result.get('industries', []))} 個產業", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--ep", help="指定單集，如 EP678")
    args = ap.parse_args()

    if not gemini_key():
        print("❌ 缺 AIza 開頭的 Gemini 金鑰：請在 repo .env 填 GOOAYE_GEMINI_KEY=AIza...")
        return 1

    from google import genai
    client = genai.Client(api_key=gemini_key())

    eps = load_episodes()
    if args.ep:
        todo = [args.ep] if args.ep in eps else []
    else:
        todo = sorted((k for k, e in eps.items() if e["status"] == "pending"),
                      key=lambda k: eps[k]["pubdate"], reverse=True)[: args.limit]
    if not todo:
        print("沒有待分析集數")
        return 0

    processed = []
    for i, key in enumerate(todo):
        try:
            analyze_one(client, key, eps[key])
            eps[key]["status"] = "done"
            save_episodes(eps)  # 逐集存檔，中斷不丟進度
            processed.append(key)
        except Exception as e:
            print(f"{key}: ❌ {e}", flush=True)
        if i < len(todo) - 1:
            time.sleep(PAUSE_S)
    print(f"完成 {len(processed)}/{len(todo)}: {', '.join(processed)}")
    # 給 daily.py 判斷要通知哪些集數
    (ANALYSES / ".last_processed.json").write_text(
        json.dumps(processed), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
