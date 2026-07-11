@echo off
cd /d C:\CLAUDE\gooaye-tracker
python scripts\daily.py --limit 4 >> data\daily.log 2>&1
