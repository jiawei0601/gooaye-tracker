#!/usr/bin/env python3
"""一次性監控：每 10 分鐘把 NIM 回填進度推 Telegram，收工即發完工報告後自我了斷。"""
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1])
TOTAL = 517

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


send(f"🏃 開始監控股癌全歷史回填（每 10 分鐘回報）。目前進度見下一則。")
last = -1
stale = 0
while True:
    t = OUT.read_text(encoding="utf-8", errors="replace")
    ok, bad = t.count("✅"), t.count("❌")
    m = re.findall(r"(EP\d+): ✅", t)
    cur = m[-1] if m else "-"
    if "ALL_DONE" in t:
        send(f"🎉 全歷史回填完成！{ok}/{TOTAL} 集成功、{bad} 失敗。"
             f"儀表板已更新並推上 GitHub：\n"
             f"https://jiawei0601.github.io/gooaye-tracker/data/dashboard.html")
        break
    if ok == last:
        stale += 1
        if stale >= 3:
            send(f"⚠️ 回填進度 30 分鐘未前進（卡在 {cur}，{ok}/{TOTAL}），"
                 f"可能 NIM 限流停批或中斷，回來後看一下。監控結束。")
            break
    else:
        stale = 0
        eta_h = (TOTAL - ok) * 65 / 3600
        send(f"📊 回填進度 {ok}/{TOTAL}（{ok*100//TOTAL}%）｜最新 {cur}｜"
             f"失敗 {bad}｜預估再 {eta_h:.1f} 小時")
    last = ok
    time.sleep(600)
