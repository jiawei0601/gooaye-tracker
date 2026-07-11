#!/usr/bin/env python3
"""抓 SoundOn RSS，合併進 data/episodes.json。

每集紀錄：{key: {title, pubdate(ISO), duration_s, audio_url, guid, status}}
status: pending(待分析) / done / skipped(早於回填起點)
"""
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from common import FEED_URL, BACKFILL_SINCE, load_episodes, save_episodes, ep_key

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def parse_pubdate(s):
    dt = datetime.strptime(s.strip(), "%a, %d %b %Y %H:%M:%S %Z")
    return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d")


def parse_duration(s):
    if not s:
        return 0
    parts = [int(p) for p in s.strip().split(":")]
    if len(parts) == 1:
        return parts[0]
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec


def fetch():
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "gooaye-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        root = ET.fromstring(r.read())

    eps = load_episodes()
    added = 0
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        enc = item.find("enclosure")
        if enc is None or not title:
            continue
        key = ep_key(title, guid)
        pubdate = parse_pubdate(item.findtext("pubDate") or "")
        if key in eps:
            eps[key]["audio_url"] = enc.get("url")  # SoundOn URL 帶時戳會更新
            continue
        eps[key] = {
            "title": title,
            "pubdate": pubdate,
            "duration_s": parse_duration(item.findtext(f"{ITUNES}duration")),
            "audio_url": enc.get("url"),
            "guid": guid,
            "status": "pending" if pubdate >= BACKFILL_SINCE else "skipped",
        }
        added += 1
    save_episodes(eps)
    pending = sum(1 for e in eps.values() if e["status"] == "pending")
    print(f"feed: {len(eps)} 集入庫, 本次新增 {added}, 待分析 {pending}")
    return eps


if __name__ == "__main__":
    fetch()
    sys.exit(0)
