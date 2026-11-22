# AGENTS.md — 專案統一規則（所有 AI agent 共用）

> Claude Code 透過 CLAUDE.md（內含 @AGENTS.md）讀本檔；Codex 等其他 agent 原生讀本檔。
> 一份規則，兩邊共用，不分叉。

## 專案慣例
- 語言 / 框架：Python 3.11+，只用標準庫（唯一外部依賴 google-genai，僅 analyze.py 用；Claude 文字分析以標準庫 urllib 直呼 Messages API，無新依賴）。
- 風格 / 命名：腳本放 scripts/、資料放 data/；分析結果一集一檔 data/analyses/EPxxx.json，
  逐字稿一集一檔 data/transcripts/EPxxx.md。
- 測試怎麼跑：`python scripts/fetch_feed.py && python scripts/aggregate.py &&
  python scripts/build_dashboard.py`（不需金鑰）；端到端 `python scripts/daily.py`。
- build / run：`python scripts/daily.py --limit 20`；排程 GooayeDaily 每日 22:00 跑
  run_daily.bat。金鑰在 .env 的 GOOAYE_GEMINI_KEY（AI Studio 金鑰、AQ. 開頭，勿 commit）。

## 跨 agent 交接紀律
- repo 是唯一真相來源；交接資訊一律寫進 repo，不可只留私有記憶（如 Claude memory）。
- 交出前：測試綠 → commit 乾淨（絕不交髒工作區）→ 更新 HANDOFF.md → 更新 issue。
- 接手前：clean tree + pull → 讀 HANDOFF.md / issue / git log / 本檔 → 先複述現況與下一步再動手。
- 架構決策寫 docs/adr/；任務狀態走 issues。

## 轉錄通道
analyze.py 有三種狀態，依 repo .env／檔案決定：
1. **Gemini 免費層**（預設）：無 `vertex-sa.json`，用 `GOOAYE_GEMINI_KEY` 直接聽音檔；有日額度限制。
2. **Vertex 付費**：repo 根有 `vertex-sa.json` 即自動切換（無日限）。
3. **Whisper**（Colab T4 faster-whisper 逐字稿，VM 端以 OpenCC s2twp 轉台灣繁體 → Gemini 文字分析，`scripts/transcribe_whisper.py`）：
   - 強制使用：`.env` 設 `GOOAYE_TRANSCRIBER=whisper`。
   - 自動備援：gemini 通道遇 429／RESOURCE_EXHAUSTED／403／PERMISSION_DENIED／billing 且 colab 可用時，
     該集改走 Whisper（episodes.json `via=whisper-fallback`）；`GOOAYE_WHISPER_FALLBACK=0` 可關閉。
   - 需要 `colab` CLI（`uv tool install google-colab-cli`，登入須使用者本人；Windows 需 `PYTHONUTF8=1`），可用 `COLAB_BIN` 指定路徑。
   - 文字分析模型由 `GOOAYE_TEXT_MODEL` 決定，預設 `claude-haiku-5-5`（可選 `claude-sonnet-5-5`／`gemini`），需 `ANTHROPIC_API_KEY`；缺金鑰自動退回 gemini。單集可用 `--text-model` 覆蓋。
   - 只測文字分析：`python scripts/analyze.py --ep EP678 --from-transcript <md>`（只印不寫）。
