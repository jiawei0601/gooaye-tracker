#!/usr/bin/env python3
"""一次性看門：等回填批次 ALL_DONE → 狀態對帳 → RAG 切塊 → (索引) → Telegram 通知。"""
import json
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


# 1. 等批次收工
while "ALL_DONE" not in OUT.read_text(encoding="utf-8", errors="replace"):
    time.sleep(60)

msgs = []

# 2. 狀態對帳：有分析檔但 status 仍 skipped/pending 的集數 → done（批次已結束，單一寫者安全）
eps = json.loads((ROOT / "data/episodes.json").read_text(encoding="utf-8"))
fixed = 0
for key, e in eps.items():
    if e["status"] != "done" and (ROOT / f"data/analyses/{key}.json").exists():
        e["status"] = "done"
        fixed += 1
(ROOT / "data/episodes.json").write_text(
    json.dumps(eps, ensure_ascii=False, indent=1), encoding="utf-8")
msgs.append(f"狀態對帳 {fixed} 集")

# 3. RAG 切塊重跑（冪等，納入全部新分析）
r = subprocess.run([sys.executable, str(ROOT / "scripts/build_rag_chunks.py")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                   cwd=str(ROOT))
tail = (r.stdout or "").strip().splitlines()
msgs.append("RAG 切塊 ✅ " + (tail[-1] if tail else "") if r.returncode == 0
            else f"RAG 切塊 ❌ rc={r.returncode}")

# 4. 索引增量更新（工具存在才跑；失敗不擋）
idx = ROOT / "scripts/rag_build_index.py"
if idx.exists():
    r2 = subprocess.run([sys.executable, str(idx)], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", cwd=str(ROOT))
    msgs.append("索引更新 ✅" if r2.returncode == 0 else f"索引更新 ❌ rc={r2.returncode}")
else:
    msgs.append("索引工具尚未就緒，切塊完成後可手動補跑")

# 5. 對帳結果 commit（批次已 push 過資料，這裡只補 episodes.json）
subprocess.run(["git", "add", "data/episodes.json"], cwd=str(ROOT))
subprocess.run(["git", "commit", "-q", "-m", "回填收工對帳：補跑集數狀態登記為 done"],
               cwd=str(ROOT))
subprocess.run(["git", "push", "-q"], cwd=str(ROOT))

send("🧩 回填後處理完成：\n" + "\n".join(f"• {m}" for m in msgs))
