# HANDOFF — gooaye-tracker

- 最後更新：Claude Code / 2026-07-12

## 任務 / 目標
追蹤台灣 podcast《股癌 Gooaye》（謝孟恭，每週三/六更新）：自動抓新集數 → Gemini 音訊
理解出摘要 → 記錄每集提及的產業與個股（含多空立場），累積成立場時間軸（比照
serenity-tracker 的模式）。每集處理完推 Telegram 摘要。

## 架構（一條管線）
RSS(SoundOn) → `fetch_feed.py`(episodes.json) → `analyze.py`(下載 mp3 → Gemini 2.5
Flash 直接吃音檔 → analyses/EPxxx.json) → `aggregate.py`(tickers.json / industries.json)
→ `build_dashboard.py`(dashboard.html) → `notify.py`(Telegram)。
`daily.py` 串全流程，`run_daily.bat` 給排程呼叫。

## 已完成
- 全套腳本（scripts/，只用標準庫 + google-genai）。
- feed 驗證：678 集全數入庫（RSS 含完整歷史），近 3 個月 26 集標 pending。
- Windows 排程 **GooayeDaily** 已註冊（每日 22:00，`run_daily.bat`，每次最多處理 4 集
  → 回填約一週自然補完，新集數優先）。
- 推播沿用 `~/.claude/telegram.env` 的 bot；回填靜音（只推發布 5 天內的集數）。

## 進行中 / 卡點
✅ 金鑰到位（2026-07-12，新版 AI Studio 金鑰為 **AQ. 開頭**，已填 .env）。
✅ EP678 端到端驗證通過：摘要/產業多空/標的論點品質良好，Telegram 已收到推播。
背景正在回填 EP677–674，其餘 pending 由排程每晚消化 4 集，約一週補完近 3 個月。

## 下一步
1. 選配：回填加深到一年/全歷史 → 手動把 episodes.json 裡 skipped 改 pending
   （或改 common.py 的 BACKFILL_SINCE 後寫個小工具重標），排程會每天自動消化。
2. 選配：標的代號校正表（見雷區的 ASTS/ALAB 問題）。

## 關鍵決策 + 為什麼
- **不用 NotebookLM**：無公開 API，只能瀏覽器模擬，脆弱且違 ToS。等效方案 = Gemini API
  直接吃音檔（NotebookLM 底層同引擎），免費層額度夠（flash 250 req/day、250k TPM，
  一集約 10 萬 token，逐集間隔 30s）。詳見 docs/adr/0002。
- **不用 YouTube 字幕**：@Gooaye 頻道字幕已關閉（yt-dlp 與 youtube-transcript-api 雙重
  確認），免費字幕路線不通。
- **不做本機 whisper**：8GB CPU 筆電轉一集 ~30 分鐘，Gemini 幾分鐘且零本機負載；
  whisper 留作 Gemini 不可用時的備援。
- 金鑰教訓：**前綴不代表有效性**。環境變數的 `GEMINI_API_KEY` 與新版 AI Studio 金鑰
  同為 AQ. 開頭，前者 401、後者可用 → 程式不做前綴檢查，只認 .env 的
  `GOOAYE_GEMINI_KEY`（不撿環境變數，避免撿到 Antigravity 的無效憑證）。
- AI Pro 訂閱額度只作用於 AI Studio 網頁介面，API key 走獨立免費層（flash 免費層
  仍在）；專案不綁 billing → 打爆頂多 429、不會扣款。

## 雷區 / 別碰
- SoundOn 音檔 URL 帶 timestamp 參數會過期 → fetch_feed 每次更新 audio_url，別存死鏈。
- Gemini 免費層 429：analyze.py 已逐集間隔 30 秒，`--limit` 別開太大一次灌。
- 音檔用完即刪（50MB/集），別改成保留，磁碟會爆。
- 標的代號可能對錯：EP678 把 Astera Labs 標成 ASTS（應為 ALAB）。純聽音檔對代號
  有極限，重要標的下單前自行核對。
- 免責：AI 生成摘要與立場標籤可能有誤，非投資建議（dashboard 與推播已標註）。

## 怎麼跑 / 怎麼測
    cp .env.example .env   # 填 GOOAYE_GEMINI_KEY=AIza...
    python scripts/daily.py --limit 4     # 全流程
    python scripts/analyze.py --ep EP678  # 單集重跑
    start data/dashboard.html             # 看儀表板
