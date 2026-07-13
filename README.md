# 股癌 Gooaye Podcast 追蹤器 🎙️

自動追蹤台灣財經 podcast《股癌》：每集音訊 → AI 分析 → **摘要＋產業觀點＋個股立場時間軸**，
累積成可搜尋的儀表板，並推播 Telegram 通知。

> 📊 **線上儀表板**：<https://jiawei0601.github.io/gooaye-tracker/data/dashboard.html>
> （每集摘要／302+ 檔標的立場演變／261+ 個產業觀點，涵蓋 2025-01 至今、每晚自動更新）

## 它做什麼

股癌每週三、六更新，每集約 50 分鐘。這個工具把「聽節目」變成「查資料庫」：

- **每集摘要**：總經判斷、討論主題、大盤看法、值得記錄的觀點
- **標的追蹤**：主持人每次提到某檔股票的立場（看多/看空/持有中/已出場）與論點，串成時間軸——
  可以看到他對一檔股票 18 個月內的完整心路（例如 PLTR：持有→出場→看空→回頭加碼）
- **產業追蹤**：同樣的時間軸邏輯套在產業層級
- **Telegram 推播**：新集數處理完自動推摘要＋提及標的

## 架構

```
SoundOn RSS ──► fetch_feed.py ──► episodes.json（集數註冊表）
                                      │
                audio (mp3) ◄─────────┤ pending 由新到舊
                    │                 │
                    ▼                 │
        Gemini 3.5 Flash 音訊理解 ◄───┘   ← 一次呼叫產出分析 JSON
                    │                        （免費層 20 集/天；或 Vertex 付費衝刺）
                    ▼
        analyses/EPxxx.json ──► aggregate.py ──► tickers.json / industries.json
                    │                                   │
                    ▼                                   ▼
        notify.py（Telegram）              build_dashboard.py ──► dashboard.html
```

單一外部依賴 `google-genai`，其餘全部 Python 標準庫。

## 快速開始

```bash
git clone https://github.com/jiawei0601/gooaye-tracker
cd gooaye-tracker
python -m pip install google-genai

cp .env.example .env        # 填入 AI Studio 的 Gemini API key（免費）
python scripts/daily.py     # 抓 feed → 分析新集數 → 彙整 → 產儀表板 → 推播
```

- 金鑰：<https://aistudio.google.com/apikey>（免費層即可，每天可處理 20 集）
- Telegram 推播（選用）：`~/.claude/telegram.env` 填 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
- 排程：Windows 工作排程器每日執行 `run_daily.bat`（或 cron 跑 `scripts/daily.py --limit 20`）

### 大量回填（選用，Vertex 付費通道）

免費層每天 20 集，回填一年份約需一週。趕時間可走 Vertex AI（GCP 試用額度可抵，
約 US$0.15/集）：建立服務帳戶（角色 Vertex AI User）、金鑰 JSON 存為 repo 根目錄
`vertex-sa.json`，管線即自動切換（需本機 ffmpeg 做音訊壓縮）。刪除該檔即回免費層。

## 改追別的 podcast

把 `scripts/common.py` 的 `FEED_URL` 換成目標節目的 RSS、調整 `analyze.py` 的 PROMPT
領域詞彙即可，管線其餘部分是通用的。

## 資料與版權聲明

- 《股癌》節目內容著作權屬於原作者**謝孟恭**。本 repo 的 `data/` 僅包含 AI 生成的
  轉化性摘要與立場標註（含少量短引句），**不含節目音訊與逐字稿**。
  若原作者對資料發佈有異議，將立即移除。
- AI 分析可能出錯（含股票代號辨識錯誤），立場標籤由模型推論、非本人確認。
- **本專案純屬資訊彙整，不構成任何投資建議。**

## License

程式碼採 [MIT](LICENSE)；資料聲明見上節與 LICENSE 附註。
