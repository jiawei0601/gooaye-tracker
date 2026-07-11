#!/usr/bin/env python3
"""gooaye-tracker 共用設定與工具。只用標準庫（google-genai 僅 analyze.py 匯入）。"""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ANALYSES = DATA / "analyses"
AUDIO = DATA / "audio"
EPISODES_JSON = DATA / "episodes.json"

FEED_URL = "https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml"
BACKFILL_SINCE = "2026-04-12"  # 近 3 個月回填起點（使用者 2026-07-12 拍板）

TELEGRAM_ENV = Path.home() / ".claude" / "telegram.env"


def load_env():
    """讀 repo 的 .env（GEMINI_API_KEY 等），已存在的環境變數優先。"""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def gemini_key():
    load_env()
    k = os.environ.get("GOOAYE_GEMINI_KEY") or os.environ.get("GEMINI_API_KEY", "")
    # Antigravity 的 OAuth 憑證（AQ. 開頭）打不通 Gemini API，需 AIza 開頭的 AI Studio 金鑰
    if not k.startswith("AIza"):
        return ""
    return k


def load_episodes():
    if EPISODES_JSON.exists():
        return json.loads(EPISODES_JSON.read_text(encoding="utf-8"))
    return {}


def save_episodes(eps):
    EPISODES_JSON.write_text(
        json.dumps(eps, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def ep_key(title, guid):
    """從標題取 EP 編號當主鍵；特別集用 guid 前 8 碼。"""
    m = re.match(r"\s*EP(\d+)", title)
    return f"EP{m.group(1)}" if m else f"SP-{guid[:8]}"
