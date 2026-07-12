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

from common import (ANALYSES, AUDIO, ROOT, TRANSCRIPTS, gemini_key,
                    load_episodes, save_episodes)

MODEL = "gemini-3.5-flash"  # 2.5-flash 已不開放給新帳號（2026-07 換帳號時發現）
PAUSE_S = 30  # 免費層 TPM 有限，一集約 10 萬 token，逐集間隔避免 429

# 有 vertex-sa.json 就走 Vertex 付費通道（吃 GCP 試用額度、無 20 集/天限制）。
# 回填衝完後刪掉本檔（或解除專案帳單連結）即回到免費層日常模式。
VERTEX_SA = ROOT / "vertex-sa.json"
_VERTEX = {"creds": None, "project": None}

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
 "quotes": ["值得記錄的觀點或提醒，1-3 條"],
 "transcript": [{{"t":"mm:ss 段落起始時間","text":"該段逐字稿，口語照實記錄"}}]
}}
規則：只記錄主持人明確討論的產業與個股，聽眾問答提到但主持人沒表態的標記 stance=觀察。
不要腦補沒提到的標的。transcript 需涵蓋全集、不可省略跳段，每段約 30-60 秒內容。
只輸出 JSON，不要 markdown 圍欄。"""


def parse_json(text):
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 輸出截斷（通常斷在最後的 transcript 陣列中途）：
        # 從尾端找最後一個完整物件，閉合陣列與外層後重試，保住分析+部分逐字稿
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


def trim_loop(transcript):
    """3.5-flash 長音訊會陷入重複迴圈（同段文字反覆出現、時間戳持續虛增）。
    同一段文字（≥20字）第 3 次出現即判定迴圈，截斷該處後回傳。"""
    counts = {}
    for i, seg in enumerate(transcript):
        t = seg.get("text", "")
        if len(t) < 20:
            continue
        counts[t] = counts.get(t, 0) + 1
        if counts[t] >= 3:
            return transcript[:i], i
    return transcript, None


def download(url, dest):
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "gooaye-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def vertex_generate(key, mp3, prompt):
    """Vertex 付費通道：ffmpeg 壓 24k 單聲道（Gemini 內部本就降到 16kbps，不損資訊）
    → inline base64 餵 global 端點。回傳輸出文字。"""
    import base64
    import subprocess

    from google.auth.transport.requests import Request as GARequest
    from google.oauth2 import service_account

    if _VERTEX["creds"] is None:
        _VERTEX["creds"] = service_account.Credentials.from_service_account_file(
            str(VERTEX_SA), scopes=["https://www.googleapis.com/auth/cloud-platform"])
        _VERTEX["project"] = json.loads(VERTEX_SA.read_text())["project_id"]
    if not _VERTEX["creds"].valid:
        _VERTEX["creds"].refresh(GARequest())

    small = mp3.with_suffix(".small.mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
                    "-ac", "1", "-b:a", "24k", str(small)], check=True)
    body = {
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": "audio/mpeg",
                            "data": base64.b64encode(small.read_bytes()).decode()}},
            {"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 65536,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    url = (f"https://aiplatform.googleapis.com/v1/projects/{_VERTEX['project']}"
           f"/locations/global/publishers/google/models/{MODEL}:generateContent")
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {_VERTEX['creds'].token}"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            resp = json.load(r)
    finally:
        small.unlink(missing_ok=True)
    cand = resp["candidates"][0]
    if cand.get("finishReason") not in (None, "STOP"):
        print(f"{key}: ⚠️ finish={cand.get('finishReason')}，輸出可能截斷", flush=True)
    return "".join(p.get("text", "") for p in cand["content"]["parts"])


def analyze_one(client, key, ep):
    mp3 = AUDIO / f"{key}.mp3"
    print(f"{key}: 下載音檔 ...", flush=True)
    download(ep["audio_url"], mp3)
    prompt = PROMPT.format(key=key, title=ep["title"], pubdate=ep["pubdate"])

    if client is None:  # Vertex 付費模式
        print(f"{key}: Vertex 分析中 ...", flush=True)
        result = parse_json(vertex_generate(key, mp3, prompt))
    else:
        from google.genai import types

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
                contents=[f, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.2, max_output_tokens=65536,  # 逐字稿一集約 3 萬 token
                    # 3.5-flash 預設 thinking 會吃 output 額度（實測 65536 可全燒在思考、正文剩 1 字）
                    thinking_config=types.ThinkingConfig(thinking_budget=0)),
            )
            finish = resp.candidates[0].finish_reason.name if resp.candidates else "?"
            if finish != "STOP":
                print(f"{key}: ⚠️ finish={finish}，輸出可能截斷", flush=True)
            result = parse_json(resp.text)
        finally:
            try:
                client.files.delete(name=f.name)
            except Exception:
                pass
    # 逐字稿獨立存 md（分析 JSON 保持精簡，dashboard 用相對路徑連過去）
    transcript = result.pop("transcript", None)
    if transcript:
        transcript, cut = trim_loop(transcript)
        if cut is not None:
            print(f"{key}: ⚠️ 逐字稿在第 {cut} 段偵測到重複迴圈，已截斷", flush=True)
        TRANSCRIPTS.mkdir(exist_ok=True)
        lines = [f"# {key} ｜ {ep['title']} — {ep['pubdate']}", ""]
        if cut is not None:
            lines.insert(1, "> ⚠️ 模型輸出在此集尾段進入重複迴圈，逐字稿於迴圈起點截斷、不完整。")
        lines += [f"[{s.get('t', '?')}] {s.get('text', '')}" for s in transcript]
        (TRANSCRIPTS / f"{key}.md").write_text("\n".join(lines), encoding="utf-8")
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

    if VERTEX_SA.exists():
        client = None  # Vertex 付費模式（見 VERTEX_SA 註解）
        pause = 3
        print("⚡ Vertex 付費模式：吃 GCP 試用額度、無日額度限制")
    else:
        if not gemini_key():
            print("❌ 缺 Gemini 金鑰：請在 repo .env 填 GOOAYE_GEMINI_KEY=（AI Studio 金鑰）")
            return 1
        from google import genai
        client = genai.Client(api_key=gemini_key())
        pause = PAUSE_S

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
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print("限流/額度耗盡，本批停止；剩餘集數留給下次排程", flush=True)
                break
        if i < len(todo) - 1:
            time.sleep(pause)
    print(f"完成 {len(processed)}/{len(todo)}: {', '.join(processed)}")
    # 給 daily.py 判斷要通知哪些集數
    (ANALYSES / ".last_processed.json").write_text(
        json.dumps(processed), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
