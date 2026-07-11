#!/usr/bin/env python3
"""把單集分析結果推 Telegram。沿用 ~/.claude/telegram.env 的 bot 設定。

用法：python scripts/notify.py EP678 [EP677 ...]
"""
import json
import sys
import urllib.parse
import urllib.request

from common import ANALYSES, TELEGRAM_ENV

TG_LIMIT = 4096


def load_tg():
    cfg = {}
    if TELEGRAM_ENV.exists():
        for line in TELEGRAM_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg.get("TELEGRAM_BOT_TOKEN"), cfg.get("TELEGRAM_CHAT_ID")


def send(token, chat_id, text):
    for i in range(0, len(text), TG_LIMIT):
        data = urllib.parse.urlencode({
            "chat_id": chat_id, "text": text[i:i + TG_LIMIT],
            "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=15)


def format_msg(a):
    lines = [f"🎙️ 股癌 {a['ep_key']} ｜ {a['title']}（{a['pubdate']}）", "",
             a.get("summary", "")]
    if a.get("market_view"):
        lines += ["", f"📊 大盤：{a['market_view']}"]
    if a.get("industries"):
        lines += ["", "🏭 產業："] + [
            f"  {i['stance']}｜{i['name']} — {i['view']}" for i in a["industries"]]
    if a.get("tickers"):
        lines += ["", "📈 標的："] + [
            f"  {t['stance']}｜{t['symbol']} {t.get('name','')} — {t['argument']}"
            for t in a["tickers"]]
    lines += ["", "（AI 彙整，非投資建議）"]
    return "\n".join(lines)


def main():
    keys = sys.argv[1:]
    if not keys:
        print("用法: notify.py EP678 [...]")
        return 1
    token, chat_id = load_tg()
    if not token or not chat_id:
        print("❌ 找不到 ~/.claude/telegram.env 的 bot 設定")
        return 1
    for key in keys:
        fp = ANALYSES / f"{key}.json"
        if not fp.exists():
            print(f"{key}: 無分析檔，跳過")
            continue
        send(token, chat_id, format_msg(json.loads(fp.read_text(encoding="utf-8"))))
        print(f"{key}: 已推播")
    return 0


if __name__ == "__main__":
    sys.exit(main())
