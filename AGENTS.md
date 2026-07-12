# AGENTS.md — 專案統一規則（Claude Code 與 Antigravity 共用）

> Claude Code 透過 CLAUDE.md（內含 @AGENTS.md）讀本檔；Antigravity 原生讀本檔。
> 一份規則，兩邊共用，不分叉。

## 專案慣例
- 語言 / 框架：Python 3.11+，只用標準庫（唯一外部依賴 google-genai，僅 analyze.py 用）。
- 風格 / 命名：腳本放 scripts/、資料放 data/；分析結果一集一檔 data/analyses/EPxxx.json，
  逐字稿一集一檔 data/transcripts/EPxxx.md。
- 測試怎麼跑：`python scripts/fetch_feed.py && python scripts/aggregate.py &&
  python scripts/build_dashboard.py`（不需金鑰）；端到端 `python scripts/daily.py`。
- build / run：`python scripts/daily.py --limit 20`；排程 GooayeDaily 每日 22:00 跑
  run_daily.bat。金鑰在 .env 的 GOOAYE_GEMINI_KEY（AI Studio 金鑰、AQ. 開頭，勿 commit）。

## 跨 agent 交接紀律
- repo 是唯一真相來源；交接資訊一律寫進 repo，不可只留私有記憶（Claude memory / Antigravity KI）。
- 交出前：測試綠 → commit 乾淨（絕不交髒工作區）→ 更新 HANDOFF.md → 更新 issue。
- 接手前：clean tree + pull → 讀 HANDOFF.md / issue / git log / 本檔 → 先複述現況與下一步再動手。
- 架構決策寫 docs/adr/；任務狀態走 issues。
