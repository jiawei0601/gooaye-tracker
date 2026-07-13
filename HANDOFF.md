# HANDOFF — gooaye-tracker

## 公開發佈（2026-07-13）
✅ GitHub 公開 repo：https://github.com/jiawei0601/gooaye-tracker（MIT）
✅ 儀表板 GitHub Pages：https://jiawei0601.github.io/gooaye-tracker/data/dashboard.html
⚠️ **逐字稿僅存本機**（版權考量已從 git 歷史整批清除、gitignore 排除）——
   dashboard 的「📄 逐字稿」連結只在本機開有效，公開版 404 屬預期行為。
   絕不能把 data/transcripts/ 重新加入版控。
- 排程每日自動 commit＋push（run_daily.bat），公開資料每晚保持最新。

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

## Vertex 衝刺 = ✅ 完成（2026-07-13）
160/160 集全數完成（2025-01-01 起），排程已恢復。EP605 模型怪癖（MAX_TOKENS 空回應）
用「無逐字稿降級」處理，是唯一沒有逐字稿的 Vertex 集數（另 EP678 之前的 33 集也無）。
⚠️ **過渡狀態**：帳單仍連著專案 → GenLang 免費層不存在（會 429 預付點數錯誤），
所以 `vertex-sa.json` 先保留、日常排程暫走 Vertex（無新集數時零成本）。
**待使用者解除專案帳單連結後**：刪 vertex-sa.json → 驗證免費層回歸 → 回到 $0 常態。
使用者屆時可順手刪 gooaye-vertex 服務帳戶與多餘的第三支 API 金鑰。

## 進行中 / 卡點
✅ 金鑰到位（2026-07-12，新版 AI Studio 金鑰為 **AQ. 開頭**，已填 .env）。
🔁 2026-07-12 晚間換到使用者的新帳號金鑰：新帳號不開放 gemini-2.5-flash，
   模型改 **gemini-3.5-flash**（analyze.py）。舊金鑰待批次收工後由使用者自行刪除。
✅ EP678 端到端驗證通過：摘要/產業多空/標的論點品質良好，Telegram 已收到推播。
🔄 回填加深到 **2025-01-01**（2026-07-12 使用者拍板）：已完成 34 集、剩 126 集。
   ⚠️ 實測新帳號免費層 = **20 次/天/模型**（GenerateRequestsPerDayPerProjectPerModel），
   夜間排程額度已對齊 20，預計 **約 7 天**補完（新集數優先、回填吃剩餘額度）。
   若想加速：可考慮第二模型分流（per-model 各有 20/天，如 gemini-3.1-flash-lite，
   品質稍弱）或短期綁計費，都需使用者拍板。

## 逐字稿（2026-07-12 加入）
✅ 同一次 Gemini 呼叫多輸出 transcript（不佔額度），獨立存 `data/transcripts/EPxxx.md`
（[mm:ss] 段落格式），dashboard 每集卡片有「📄 逐字稿」連結。
EP678 已實測：52分鐘全集 60 段 22,884 字、finish=STOP 無截斷（用舊金鑰+2.5-flash 驗證）。
⚠️ **3.5-flash 兩個實測坑已修**（2026-07-12，外部轉寫 110 分音檔踩到）：
1. 預設 thinking 會吃光 output token（65536 全燒在思考、正文剩 1 字）→ analyze.py 已加
   `thinking_budget=0`；2. 長音訊會陷入重複迴圈＋時間戳虛增 → 已加 `trim_loop()` 偵測
   截斷＋finish_reason 警告。首晚回填仍要抽查 2-3 集逐字稿結尾完整性。
⚠️ 既有 33 集（EP678 以外）沒有逐字稿；要補得重聽一次、每集佔 1 次額度，選配。

## 下一步
1. 看 `data/daily.log` 與 episodes.json pending 數，確認回填每日消化進度；
   抽查 3.5-flash 產出的逐字稿品質。
2. 選配：再加深到全歷史（2020 起 518 集 skipped）→ 改 BACKFILL_SINCE 後重標。
3. 選配：標的代號校正表（見雷區的 ASTS/ALAB 問題）。

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
