@echo off
cd /d C:\CLAUDE\gooaye-tracker
python scripts\daily.py --limit 20 >> data\daily.log 2>&1
git add -A >nul 2>&1
git commit -q -m "daily: 排程自動入庫分析/逐字稿/儀表板" >nul 2>&1
