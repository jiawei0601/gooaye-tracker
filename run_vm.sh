#!/bin/bash
# Hermes VM 排程進入點：cron 週三/六 17:05、20:05（台北時間，股癌約 16:00 上架）
cd "$(dirname "$0")"
git pull -q --rebase origin master
.venv/bin/python scripts/daily.py --limit 20
git add -A
git commit -q -m "daily: VM 排程自動入庫分析/儀表板" || true
git push -q origin master
