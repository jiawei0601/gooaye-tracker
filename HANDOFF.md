# HANDOFF — gooaye-tracker

## RAG 系統 = ✅ 最終完成（2026-07-14 01:10）
**50,695 塊全量入庫、向量 100%、孤兒已清**。六類抽取 678 集全完成（DeepSeek 官方，
零失敗，成本 ~US$3）。各類：transcript 23,751/qa 4,669/ticker 4,158/wisdom 3,897/
joke 3,473/chat 3,454/industry 2,578/quote 2,016/macro 1,350/summary 678/market_view 671。
查詢：`python scripts/rag_query.py --q "..." [--kind --category --symbol --industry --stance
--since --until --ep] [--mode keyword|semantic|hybrid]`。
維運：新集數由 VM 排程產分析；六類抽取與 RAG 更新目前**手動**（extract_extras.py
--provider deepseek → build_rag_chunks.py → rag_build_index.py，全冪等），可併入 run_vm.sh（選配）。
下一步選配：接進 gooaye-perspective skill 的 Step 2（讓分身引用本機檢索回答）。

## 六類抽取整合進 RAG（2026-07-14，整合 agent 交付）
✅ `scripts/build_rag_chunks.py`／`rag_build_index.py`／`rag_query.py` 已擴充，
把 `data/extras/EPxxx.json` 六類（qa/chat/joke/wisdom/macro，ads 依上一條政策排除）
切塊進 `data/rag/extras_chunks.jsonl`，一語意單位一塊、id 格式 `EPxxx-x-{kind}-{序號}`。
- `chunks` 表新增 `category` 欄（nullable，ALTER TABLE 相容既有 db，非破壞性）。
- `rag_query.py` 新增 `--category`（子字串比對）；`--kind` 新增 qa/chat/joke/wisdom/macro
  （不含 ad，見上一條政策）；extras 六類的 metadata 段顯示 category 而非 symbol/stance。
- 交付時跑過一輪 build→index，49,687 塊、embeddings 全補齊（NIM 間歇 500 錯誤但重跑會
  自動補完，非阻塞）。**注意**：交付前發現 `scripts/build_rag_chunks.py` 已被另一個
  session（同一工作目錄）依「業配不進 RAG」政策改過並 commit（d9ea877/6278698），
  本次交付是在該版本基礎上補上 index/query 層，未動搖該政策。
- 觀察到 `scripts/_post_extras.py`（未進版控的滾動看門腳本）：每 10 分鐘偵測抽取批次
  進度，偵測到本次交付（extras 支援）後會自動接手跑 build→index 直到批次 ALL_DONE，
  期間會檢查 `rag_build_index` 是否已在跑以避免撞寫；本次交付未改動該檔，僅供知悉。
- 之後抽取批次持續完成新集數時，重跑 `build_rag_chunks.py`→`rag_build_index.py`
  即可增量補齊（冪等，已驗證兩次重跑 chunker 輸出逐位元組一致）。

## RAG 整理政策（2026-07-14 使用者指示）
- **業配（ad）不進 RAG**：切塊層排除、庫中 508 塊已清（含向量與 FTS rebuild）；
  原始 sponsor 紀錄留在 data/extras/ 備查。日後改政策把 build_rag_chunks.py 的
  ads 段落還原即可。

## Embedding 災備路線（2026-07-14 查證）
主通道=NIM `baai/bge-m3`（免費）。若 NIM embedding 卡死（比照 GLM-5.2 前例）：
OpenRouter 2025-11 起支援 embeddings（`https://openrouter.ai/api/v1/embeddings`，OpenAI 相容格式），
**模型清單含同款 bge-m3** → 換 URL＋OPENROUTER_API_KEY 即可接續現有向量不必全庫重嵌；
成本 ~$0.01-0.02/M tokens（全庫重嵌也才 ~$0.3、日常增量趨近 $0）。
換「不同」embedding 模型才需要全庫重嵌（向量空間不相容）。

## 美股ticker代號誤植審計（2026-07-13）
✅ 用 `data/external/wmrs/transcripts.json`（678集逐字稿）比對全庫美股ticker，
修正 51 筆誤植（39集）→ `git 962fd7f`。報告見 `data/audit_us_symbols.md`。
兩類主因：(1) symbol欄位誤填公司全名而非真實代號（如 Qualcomm→應為QCOM）；
(2) 少數集數用了錯誤但真實存在的代號（如 LUMN 誤植為 Lumentum，LUMN實為
不相關的 Lumen Technologies，真實代號應為 LITE）。已跑 aggregate/build_dashboard/
build_rag_chunks，tickers.json 807→782檔（消除孤兒重複）。
⚠️ 14 筆待裁決未動（私人公司如SpaceX/Anthropic無代號、非美股market誤標如CATL/
Hynix/Kering）清單在報告內，需使用者拍板是否處理。
⚠️ 未跑 rag_build_index.py（避免撞embedding背景程序寫gooaye.db），索引更新待下次整合。
⚠️ 發現 EP565.json 的 tickers 是扁平字串陣列而非物件陣列（既有schema異常，僅1集），
本輪未修，記錄提醒。

## 網路逐字稿源（2026-07-13）
✅ 發現粉絲站 **whatmkreallysaid.com**：678 集全集逐字稿，站方以 `transcripts.json.br`
單檔打包（前端搜尋用），一個請求全拿。已寫 `scripts/fetch_web_transcripts.py`
一次性入庫 678 集 → `data/transcripts_web/`（38MB）。
- 本機排程 **GooayeWebSync**（每日 23:00，`run_web_sync.bat`）增量同步：先抓輕量
  episodes.json 比對，無新集數不下載大包；log 在 data/web_sync.log。
- ⚠️ 版權雷區同 data/transcripts/：**僅存本機、已 gitignore、絕不能進公開 repo**。
- 影響：全歷史 518 集不再需要 Gemini 音訊轉寫（原「綁計費衝刺」方案作廢）；
  自產 transcripts/（Gemini）與站方 transcripts_web/ 並存，前者含 [mm:ss] 時間戳、
  後者是站方清洗過的段落格式。分析管線（analyses/ 產業個股立場）不受影響、照舊。

## 排程遷移 Hermes VM（2026-07-13）
✅ 生產排程改在 **Hermes VM**（hermes-gw, 35.254.238.132, chang 使用者）：
   cron `5 17,20 * * 3,6`（台北時間週三/六 17:05＋20:05 補漏；股癌約 16:00 上架）
   → `~/gooaye-tracker/run_vm.sh`（pull→分析→commit→push），log 在 VM data/daily.log。
- VM 端：venv `.venv/`、金鑰 `~/gooaye-tracker/.env`＋`~/.claude/telegram.env`（皆 600）、
  push 走 deploy key（repo 設定 hermes-vm-daily-push）。
- 本機 GooayeDaily 排程**已停用**（避免雙邊 push 衝突）；本機要手動跑先 `git pull`。
- 公開版 dashboard 由 VM 產出（無逐字稿連結）；本機看逐字稿直接開 data/transcripts/。
✅ 2026-07-13 使用者已解除專案帳單連結，免費層實測復活；vertex-sa.json 已刪，
   系統進入最終形態：VM 免費層全自動、$0 長期營運。

## 全歷史回填 = ✅ 完成（2026-07-13 晚）
678/678 集全數入庫（2020-02 開播起）：**807 檔標的、755 個產業**時間軸，公開儀表板已更新。
- EP1-518 走文字分析（wmrs 逐字稿）；EP519-678 為原 Gemini 音訊分析。
- ⚠️ 事故紀錄：NIM GLM-5.2 中途降速（60-90秒/集 → 5分/集，ping 90 秒無回應），491 集
  切 **DeepSeek 官方**（`analyze_text.py --provider deepseek`）收尾：7-12秒/集、零失敗、
  總成本 ~US$2.5。教訓=NIM 免費端點適合不趕時間的批次，趕進度用官方付費（快 40 倍）。
- 模型對比實測（EP518/EP534，詳見對話紀錄）：回填=DeepSeek官方最優；Gemini 3.5 Flash
  文字模式會幻覺台股代號（茂達→3012 錯，應為 6138），只留音訊管線用；抽取=v4-pro 召回
  遠勝 Gemini（22 vs 8 項）。
- RAG 切塊已自動重跑：analysis_chunks 10,044 塊（全 678 集）。

## RAG 語料切塊（2026-07-13，階段 1 完成）
✅ `scripts/build_rag_chunks.py`（sonnet 實作、haiku read-back 全過）→ `data/rag/`（gitignore，僅本機）：
- transcript_chunks.jsonl：23,751 塊（own 126 集帶時間戳優先、wmrs 552 集補），~700字/塊+100重疊
- analysis_chunks.jsonl：2,606 塊（摘要/大盤/標的立場/產業/金句 一語意一塊）
⚠️ NIM 全歷史回填完成後要**重跑本腳本**納入新增分析（analysis_chunks 會長到 ~9k 塊）。
下一階段待使用者拍板：embedding 模型、索引落點（本機 vs Hetzner 比照 civil-rag）、查詢介面。

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
✅ 收尾完成（2026-07-13）：帳單已解除、免費層驗證復活、vertex-sa.json 已刪。
選配清理（使用者自便）：主控台刪 gooaye-vertex 服務帳戶與多餘的第三支 API 金鑰。

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
