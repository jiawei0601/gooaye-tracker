# ADR-0002: 用 Gemini 音訊理解取代「轉錄＋摘要」兩段式管線

- 日期：2026-07-12
- 狀態：Accepted

## 背景
股癌是音訊 podcast（每集 ~50 分鐘）。原始構想有四條路：
YouTube 字幕（免費）、NotebookLM、本機 whisper 轉錄＋LLM 摘要、雲端 STT。

## 決策
下載 RSS mp3 → Gemini Files API 上傳 → gemini-2.5-flash 一步輸出
結構化 JSON（摘要/產業/標的/立場）。

## 理由
- YouTube 字幕：@Gooaye 頻道已關閉字幕（yt-dlp + youtube-transcript-api 雙重確認），不通。
- NotebookLM：無公開 API，自動化只能瀏覽器模擬，脆弱且違 ToS；其底層即 Gemini，
  走 Gemini API 等效且可排程。
- 本機 whisper：8GB CPU 筆電一集 ~30 分鐘，回填 26 集要 13 小時；且還需第二段 LLM。
- Gemini 免費層：flash 250 req/day、250k TPM；一集音訊 ~10 萬 token，
  每日 4 集配額綽綽有餘，成本 $0。

## 後果
- 依賴 Google 免費層政策；若收緊，備援 = faster-whisper（夜間慢跑）＋ GLM-5.2 NIM 摘要。
- 需要一支 AI Studio 金鑰（AIza 開頭）；Antigravity 的 OAuth 憑證不可用。
