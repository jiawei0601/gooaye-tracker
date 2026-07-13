#!/usr/bin/env python3
"""滾動看門：每 10 分鐘把「新完成的六類抽取」增量整合進切塊與索引；
抽取批次 ALL_DONE 且最後一輪整合完 → 發完工總結後退出。"""
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1])

cfg = {}
for line in (Path.home() / ".claude" / "telegram.env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()


def send(text):
    data = urllib.parse.urlencode(
        {"chat_id": cfg["TELEGRAM_CHAT_ID"], "text": text}).encode()
    urllib.request.urlopen(urllib.request.Request(
        f"https://api.telegram.org/bot{cfg['TELEGRAM_BOT_TOKEN']}/sendMessage",
        data=data), timeout=15)


def index_busy():
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\").CommandLine"],
            capture_output=True, text=True, timeout=60)
        return "rag_build_index" in (r.stdout or "")
    except Exception:
        return False  # 偵測不了就當不忙：索引腳本本身對重複執行有防護（增量跳過）


def extras_supported():
    """整合 agent 交付後 build_rag_chunks.py 才認得 extras；未交付前先不整合。"""
    return "extras" in (ROOT / "scripts/build_rag_chunks.py").read_text(encoding="utf-8")


def run(script):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(ROOT)).returncode == 0


last_integrated = -1
while True:
    n = len(list((ROOT / "data/extras").glob("EP*.json")))
    done = "ALL_DONE" in OUT.read_text(encoding="utf-8", errors="replace")

    if extras_supported() and not index_busy() and (n > last_integrated or done):
        ok = run("build_rag_chunks.py") and run("rag_build_index.py")
        if ok:
            delta = n - max(last_integrated, 0)
            last_integrated = n
            send(f"🔄 增量整合：{n} 集六類內容已入索引（+{delta}）"
                 + ("｜抽取批次已全部完成 🎉" if done else ""))
        else:
            send(f"⚠️ 增量整合失敗（{n} 集時），10 分鐘後重試")
    elif not extras_supported():
        pass  # 整合工具未交付，先等

    if done and last_integrated >= n:
        send("✅ 六類抽取全量整合收工，RAG 索引為最終完整狀態。")
        break
    time.sleep(600)
