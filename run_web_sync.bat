@echo off
rem 每晚 23:00 增量同步 whatmkreallysaid.com 逐字稿（無新集數就只抓一個小索引檔）
cd /d C:\CLAUDE\gooaye-tracker
set PYTHONIOENCODING=utf-8
python scripts\fetch_web_transcripts.py >> data\web_sync.log 2>&1
