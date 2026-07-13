#!/usr/bin/env python3
"""非標的內容抽取：把每集逐字稿（data/external/wmrs/transcripts.json）丟給 NIM，
抽取聽眾問答/閒聊/笑點/投資心法/總經看法/業配六類，輸出 data/extras/EPxxx.json。

只讀 transcripts.json，不動 build_rag_chunks.py / rag_build_index.py / rag_query.py /
analyze*.py / episodes.json（其他程序在用）。data/extras/ 不進版控（見 .gitignore）。

可中斷續跑（已有 extras 檔的集數自動跳過）。

用法：
  python scripts/extract_extras.py               # 全部未跑集數，新到舊
  python scripts/extract_extras.py --limit 3     # 限量（試跑用）
  python scripts/extract_extras.py --ep EP534    # 指定單集，可逗號分隔多集
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Windows 主控台預設 cp950，印中文會炸；統一改 UTF-8（比照 common.py 作法，不 import 避免耦合）
for _s in (sys.stdout, sys.stderr):
    if _s and _s.encoding and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EXTRAS = DATA / "extras"
WMRS = DATA / "external" / "wmrs" / "transcripts.json"

NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODEL = "deepseek-ai/deepseek-v4-pro"  # 勿用 z-ai/glm-5.2，另一個回填程序在用，避開限流桶
MAX_TX_CHARS = 60_000  # 逐字稿防護，超長截斷並在輸出標記 truncated

PROMPT = """你是台灣 podcast《股癌 Gooaye》(主持人謝孟恭) 第 {key} 集「{title}」({date}) 的
逐字稿分析師。這集逐字稿如下（見文末全文）。請只抽取「非投資標的」的六類內容，
輸出 JSON（繁體中文），格式：
{{
 "qa": [{{"category":"投資心態|職涯|感情|人生|其他","question":"聽眾問題一句話","answer_gist":"回答要旨1-2句"}}],
 "chat": [{{"topic":"育兒|健身減重|咖啡|遊戲|旅遊|3C|其他","note":"聊了什麼一句話"}}],
 "jokes": ["好笑的哏/自嘲/荒謬類比，保留原味 1-2 句"],
 "wisdom": ["不掛特定標的的投資心法論述（部位/停損/心態/資訊判讀），每條 1-3 句"],
 "macro": [{{"topic":"關稅|央行|地緣|政策|其他","view":"他的看法 1-2 句"}}],
 "ads": [{{"sponsor":"業配對象","note":"一句話"}}]
}}
規則：
- 不要抽取個股/產業標的相關內容（那部分由別的程序處理）。
- 每個類別沒內容就給空陣列 []，不要腦補、不要無中生有、不要把其他類別的內容硬塞進來。
- category/topic 欄位盡量用給定選項，真的不合適才用「其他」。
- 只輸出 JSON，不要 markdown 圍欄、不要任何說明文字。"""


def parse_json(text):
    """複製自 analyze.py 的截斷救援邏輯（不 import，避免耦合到分析主流程）。"""
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pos = len(text)
        for _ in range(50):
            pos = text.rfind("}", 0, pos)
            if pos <= 0:
                break
            try:
                return json.loads(text[: pos + 1] + "]}")
            except json.JSONDecodeError:
                continue
        raise


def nim_generate(key, prompt, transcript_text):
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
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                resp = json.load(r)
            return resp["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429 or 500 <= e.code < 600:
                last_err = e
                print(f"{key}: ⚠️ HTTP {e.code}，30秒後重試（{attempt + 1}/3）", flush=True)
                time.sleep(30)
                continue
            raise
    raise last_err


def extract_one(ep):
    key = f"EP{ep['n']}"
    tx = ep.get("tx") or ""
    truncated = len(tx) > MAX_TX_CHARS
    if truncated:
        tx = tx[:MAX_TX_CHARS]
    prompt = PROMPT.format(key=key, title=ep.get("t", ""), date=ep.get("d", ""))
    result = parse_json(nim_generate(key, prompt, tx))
    out = {
        "ep_key": key,
        "date": ep.get("d", ""),
        "title": ep.get("t", ""),
        "qa": result.get("qa") or [],
        "chat": result.get("chat") or [],
        "jokes": result.get("jokes") or [],
        "wisdom": result.get("wisdom") or [],
        "macro": result.get("macro") or [],
        "ads": result.get("ads") or [],
    }
    if truncated:
        out["truncated"] = True
    return key, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10**6)
    ap.add_argument("--ep", help="指定單集如 EP534，可逗號分隔多集")
    args = ap.parse_args()

    if not os.environ.get("NVIDIA_NIM_API_KEY"):
        print("❌ 缺 NVIDIA_NIM_API_KEY", flush=True)
        return 1

    EXTRAS.mkdir(parents=True, exist_ok=True)
    wmrs = json.loads(WMRS.read_text(encoding="utf-8"))

    if args.ep:
        wanted = set(args.ep.split(","))
        todo = [e for e in wmrs if f"EP{e['n']}" in wanted]
    else:
        todo = sorted(wmrs, key=lambda e: e["n"], reverse=True)

    todo = [e for e in todo if not (EXTRAS / f"EP{e['n']}.json").exists()][: args.limit]
    print(f"待抽取 {len(todo)} 集", flush=True)

    fails = 0
    done = 0
    for ep in todo:
        key = f"EP{ep['n']}"
        if not ep.get("tx"):
            print(f"{key}: ⚠️ 逐字稿缺此集，跳過", flush=True)
            continue
        try:
            key, out = extract_one(ep)
            (EXTRAS / f"{key}.json").write_text(
                json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
            done += 1
            fails = 0
            print(f"{key}: ✅ qa={len(out['qa'])} chat={len(out['chat'])} "
                  f"jokes={len(out['jokes'])} wisdom={len(out['wisdom'])} "
                  f"macro={len(out['macro'])} ads={len(out['ads'])} "
                  f"({done}/{len(todo)})", flush=True)
        except Exception as e:
            fails += 1
            print(f"{key}: ❌ {e}", flush=True)
            if fails >= 5:
                print("連續失敗 5 次，停批（NIM 可能異常）", flush=True)
                break
        time.sleep(2)
    print(f"完成 {done} 集", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
