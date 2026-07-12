@echo off
cd /d C:\CLAUDE\gooaye-tracker
python scripts\daily.py --limit 8 >> data\daily.log 2>&1
