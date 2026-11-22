#!/usr/bin/env python3
"""Whisper 備援通道：在 Google Colab T4 上用 faster-whisper 產生逐字稿。

流程：本機呼叫 `colab run --gpu T4 colab_whisper_job.py <audio_url> <key> <model>`，
Colab VM 自行下載音檔並轉錄，stdout 即逐字稿（# 標頭＋每行 [mm:ss] 文字），不需下載音檔到本機。
前置：`uv tool install google-colab-cli` 並完成 colab 登入（需使用者本人）。

用法：
  python scripts/transcribe_whisper.py --ep EP678
  python scripts/transcribe_whisper.py --ep EP678 --out C:/tmp/EP678.md --model large-v3
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from common import TRANSCRIPTS, load_episodes

JOB_SCRIPT = Path(__file__).resolve().parent / "colab_whisper_job.py"
LOG_FILE = TRANSCRIPTS / ".whisper.log"
_TS_LINE = re.compile(r"^\[\d{1,3}:\d{2}(?::\d{2})?\]", re.M)


def find_colab():
    """回傳 colab 執行檔路徑；找不到回傳 None。"""
    return os.environ.get("COLAB_BIN") or shutil.which("colab")


def whisper_transcript(key: str, audio_url: str, model: str = "large-v3",
                       timeout: int = 2400) -> str:
    colab = find_colab()
    if not colab:
        raise RuntimeError("找不到 colab CLI：請執行 `uv tool install google-colab-cli`，"
                           "或用環境變數 COLAB_BIN 指定路徑")
    env = dict(os.environ, PYTHONUTF8="1")
    # 固定 session 名稱：colab run 的本機程序若被殺（逾時、cron 中斷），VM 會留著計費，
    # 有名字才能在 finally 裡可靠地 stop。colab run 正常結束時自己會 stop，重複 stop 無害。
    session = f"gooaye-{key}".lower()
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            [colab, "run", "--gpu", "T4", "-s", session, str(JOB_SCRIPT), audio_url, key, model],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
            env=env, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} {key} TIMEOUT {timeout}s =====\n"
                    f"{(e.stderr or b'').decode('utf-8', 'replace') if isinstance(e.stderr, bytes) else (e.stderr or '')}\n")
        raise RuntimeError(f"Whisper 轉錄逾時（{timeout}s），session {session} 已嘗試關閉")
    finally:
        subprocess.run([colab, "stop", "-s", session], stdin=subprocess.DEVNULL,
                       capture_output=True, env=env, timeout=120)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} {key} rc={r.returncode} =====\n"
                f"{r.stderr}\n")
    out = r.stdout
    n_ts = len(_TS_LINE.findall(out))
    if r.returncode != 0 or not out.startswith("# ") or n_ts < 20:
        tail = "\n".join(r.stderr.strip().splitlines()[-5:])
        raise RuntimeError(f"Whisper 轉錄失敗 returncode={r.returncode} "
                           f"時間戳行數={n_ts}\n{tail}")
    return out


def transcript_to_text(md: str) -> str:
    """去掉標頭與 [mm:ss] 時間戳，合併成純文字給分析用。"""
    parts = []
    for line in md.splitlines():
        if line.startswith("#") or line.startswith(">"):
            continue
        line = _TS_LINE.sub("", line).strip()
        if line:
            parts.append(line)
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep", required=True, help="集數 key，如 EP678")
    ap.add_argument("--out", help="輸出路徑，預設 data/transcripts/{key}.md")
    ap.add_argument("--model", default="large-v3")
    args = ap.parse_args()

    eps = load_episodes()
    if args.ep not in eps:
        print(f"❌ episodes.json 無 {args.ep}")
        return 1
    out = Path(args.out) if args.out else TRANSCRIPTS / f"{args.ep}.md"
    t0 = time.time()
    md = whisper_transcript(args.ep, eps[args.ep]["audio_url"], args.model)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"✅ {args.ep}: {len(_TS_LINE.findall(md))} 行、{time.time() - t0:.0f} 秒 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
