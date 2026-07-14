# 美股代號誤植審計報告（2026-07-13）

## 統計
- 掃描美股 ticker 筆數：2244
- 確認正確：2179
- 修正（高信心）：51（含二輪fuzzy比對補漏 3 筆：EP641 LUMN→LITE、EP449 NXP→NXPI、EP328 IFX→IFNNY）
- 待使用者裁決（可疑，未動）：14

## 方法
1. `scripts/_audit_us_symbols.py`：對 678 集全部 analyses 檔的每筆 US ticker，
   在 `data/external/wmrs/transcripts.json` 對應集數逐字稿裡找 symbol／公司名字串證據，
   並套用已知混淆對照表（EP678 ASTS→ALAB、EP640 AOI→AAOI 由此自動修正）。
2. 人工複查：對「name 欄位＝symbol 欄位」「symbol 非標準代號格式（含小寫/空格/中文）」
   的孤兒代號逐一讀語境判斷；並用「同一公司名在資料庫其他集已有的正確代號」做內部一致性
   交叉比對，抓出少數集數的誤植（即使不是多數）。
3. WebSearch 驗證冷門/新上市公司真實代號（FANGDD→DUO、TSLA 2x ETF→TSLL、
   Firefly Aerospace→FLY 等）。

## 修正清單（代號層級聚合）

| 誤植代號 → 正確代號 | 公司 | 筆數 | 集數 |
|---|---|---|---|
| ASTS → ALAB | Astera Labs | 1 | EP678 |
| ALTR → ALAB | Astera Labs | 1 | EP642 |
| AOI → AAOI | Applied Optoelectronics | 3 | EP362, EP507, EP640 |
| NXP → NXPI | 恩智浦半導體 | 4 | EP169, EP196, EP474, EP449 |
| LUMN → LITE | Lumentum | 5 | EP618, EP620, EP634, EP642, EP641 |
| ALST → CLS | Celestica | 1 | EP584 |
| GSTAT → GSAT | Globalstar | 1 | EP175 |
| CDPR → CDR | CD Projekt | 1 | EP122 |
| LVMH → LVMUY | LVMH（美股OTC ADR） | 1 | EP171 |
| IFX → IFNNY | Infineon（美股OTC ADR，同集market標US） | 1 | EP328 |
| Tesla → TSLA | Tesla | 3 | EP623, EP631, EP677 |
| Qualcomm → QCOM | Qualcomm | 1 | EP500 |
| Broadcom → AVGO | Broadcom | 1 | EP500 |
| Microsoft → MSFT | Microsoft | 1 | EP500 |
| Impinj → PI | Impinj | 1 | EP512 |
| Adobe → ADBE | Adobe | 2 | EP513, EP668 |
| CoreWeave → CRWV | CoreWeave | 2 | EP537, EP563 |
| Amphenol → APH | Amphenol | 2 | EP560, EP623 |
| Rogers → ROG | Rogers Corporation | 1 | EP560 |
| Sony → SONY | Sony | 1 | EP597 |
| Credo → CRDO | Credo | 1 | EP623 |
| Ryanair → RYAAY | Ryanair Holdings | 1 | EP629 |
| Google → GOOGL | Google | 1 | EP664 |
| Intel → INTC | Intel | 1 | EP664 |
| VISHAY → VSH | Vishay | 1 | EP665 |
| 美光 → MU | Micron | 1 | EP666 |
| Nvidia → NVDA | Nvidia | 1 | EP670 |
| Palantir → PLTR | Palantir | 1 | EP670 |
| Texas Instruments → TXN | Texas Instruments | 1 | EP671 |
| 德州儀器 → TXN | Texas Instruments | 1 | EP672 |
| 安森美 → ON | ON Semiconductor | 1 | EP672 |
| Zillow → Z | Zillow | 1 | EP83 |
| Opendoor → OPEN | Opendoor | 1 | EP83 |
| Redfin → RDFN | Redfin | 1 | EP83 |
| TSLA 2x ETF → TSLL | Direxion TSLA 2x ETF | 1 | EP496 |
| FANGDD → DUO | 房多多 | 1 | EP45 |
| FLY（symbol不變，name修正 Flywire→Firefly Aerospace） | Firefly Aerospace | 1 | EP670 |

**合計 51 筆修正**，逐筆證據見 `data/_audit_manual_fixes.json`（分兩輪套用腳本產生：
第一輪46筆＋第二輪fuzzy比對補漏3筆＋FLY name-only修正因腳本重跑重複記錄1次，
實際獨立修正51筆）。

## 待使用者裁決（可疑，未動）

| EP | symbol | name | 原因 |
|---|---|---|---|
| EP509 | Anduril Industries | Anduril Industries | 私人公司，無公開股票代號，無法指派真實ticker |
| EP512 | Zippin | Zippin (無人商店新創) | 私人公司，無公開股票代號 |
| EP563 | Anduril | Anduril Industries | 私人公司，無公開股票代號 |
| EP629 | SpaceX | SpaceX | 私人公司，無公開股票代號 |
| EP647 | SpaceX | SpaceX | 同上 |
| EP665 | SpaceX | SpaceX | 同上 |
| EP670 | SpaceX | SpaceX | 同上 |
| EP674 | SpaceX | SpaceX | 同上 |
| EP664 | Anthropic | Anthropic | 私人公司，無公開股票代號 |
| EP664 | xAI | xAI | 私人公司，無公開股票代號 |
| EP670 | VAST | Vast Space | 逐字稿該段落僅提及「RKLB、ASTS或是Fly」三檔，未見VAST/Vast Space字樣；Vast Space（太空站新創）目前查無公開上市紀錄，疑為模型幻覺附加，建議使用者確認是否應刪除此筆 |
| EP165 | 300750 | 寧德時代 | market欄位誤標US，300750為深圳創業板真實代號（CATL），非美股，本輪不處理market欄位 |
| EP402 | Hynix | SK海力士 | market欄位誤標US，SK海力士主要在韓國KRX上市（000660），無活躍美股代號，本輪不處理 |
| EP171 | KERING | Kering | market欄位誤標US，Kering主要在Euronext Paris上市，本輪不處理market欄位（LVMH同集已修正為OTC ADR LVMUY，但Kering無同等常用ADR，故未動） |

## 附註
- `data/analyses/EP565.json` 的 `tickers` 欄位是扁平字串陣列（非物件陣列），為既有
  schema異常（僅此1集），本次審計範圍不含結構修正，僅記錄提醒。
- FB/META（Facebook 2022年6月才改名改代號）：EP1-518區間多筆FB記錄實際發生於改名前，
  屬歷史正確，非誤植，未列入修正或待裁決。

| EP673 | LUMN | LITE | Lumen | Lumentum | 指揮官複核抽查發現：原文為「Coherent、Lumentum 跟 Marvell」光通語境 |

## 裁決處理紀錄（2026-07-13，使用者核准「按建議處理、以逐字稿為準」）
- 私人公司 10 筆（SpaceX×5/Anduril×2/Anthropic/xAI/Zippin）→ market=private 保留追蹤；
  Anduril 主鍵統一（Anduril Industries→Anduril）
- EP670 VAST → 刪除（逐字稿該段僅 RKLB/ASTS/Fly，無 VAST 佐證）
- EP165 300750(CATL)/EP402 Hynix/EP171 KERING → market=other（非美股）
- EP565 tickers 扁平字串 schema 異常 → DeepSeek 官方重新分析取代（5 檔正常物件）
- 彙整後 781→758 檔（EP565 舊字串垃圾鍵清除＋合併）

| EP677 | CLSK | NET | CleanSpark | Cloudflare | 使用者指正：原文「Palantir、CrowdStrike 跟 CloudFlare 這幾支我最愛」，Gemini 音訊把 CloudFlare 誤聽為 CleanSpark |
