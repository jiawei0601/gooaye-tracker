#!/usr/bin/env python3
"""比對 data/transcripts/EPxxx.md（Gemini 音訊轉寫）與
data/external/wmrs/transcripts.json（人工修正權威版），
找出音訊版可能聽錯的美股代號/公司名，並交叉分析是否污染 data/analyses/EPxxx.json。

只讀不改；輸出 data/audit_transcript_diff.md。
純標準庫。PYTHONIOENCODING=utf-8 執行。
"""
import difflib
import json
import re

from common import ROOT, DATA, ANALYSES, TRANSCRIPTS

WMRS = DATA / "external" / "wmrs" / "transcripts.json"
OUT_MD = DATA / "audit_transcript_diff.md"

TS_RE = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]\s*")
HEADER_RE = re.compile(r"^#.*$", re.M)

# 已知常見的非代號英文縮寫（雜訊來源：AI 產業用語、通用縮寫、平台名稱等），過濾掉不當代號疑點
ACRONYM_STOPWORDS = {
    "AI", "US", "TW", "EPS", "ROE", "ROI", "GDP", "CEO", "CFO", "CTO", "COO",
    "IPO", "ETF", "ASIC", "NAND", "SOP", "ID", "PS", "HBO", "TPU", "LPU",
    "GTC", "QA", "ATH", "FOMC", "ISM", "PMI", "YOY", "QOQ", "WSJ", "NYT",
    "ECB", "FED", "ATM", "IC", "PC", "TV", "VR", "AR", "XR", "OK", "LOL",
    "DIY", "FYI", "GPU", "CPU", "RAM", "SSD", "OS", "APP", "APP", "URL",
    "API", "SDK", "CDN", "VPN", "FBI", "CIA", "NBA", "MLB", "NFL", "IG",
    "FB", "YT", "PR", "HR", "R&D", "B2B", "B2C", "SaaS", "MOM", "YOY",
    "Q1", "Q2", "Q3", "Q4", "H1", "H2", "GTM", "KPI", "OKR", "TSMC",
    "CES", "WWDC", "NFT", "DEFI", "DEX", "CEX", "DAO", "ESG", "CPI",
    "PPI", "GNP", "OECD", "IMF", "WHO", "CDC", "EU", "UK", "UN", "NASA",
    "SEC", "FDA", "DOJ", "FTC", "USB", "LED", "OLED", "LCD", "CMOS",
    "WIFI", "GPS", "SIM", "NFC", "AGI", "LLM", "GPT", "TTS", "STT",
    "OCR", "NLP", "AR", "VR", "MR", "IOT", "5G", "4G", "3G", "K", "M",
    "B", "T", "OK", "TBD", "ASAP", "EOD", "COB", "NDA", "MOU", "RFP",
    "CAGR", "TAM", "SAM", "SOM", "MVP", "UI", "UX", "QC", "QC",
}

# 代號/名稱恰好撞到常見英文單字，容易在中英夾雜語境下誤判（如 "based ON"、"Open AI"、
# "quarter ON quarter"、"the Team"），一律排除，不當作可辨識代稱
COMMON_WORD_COLLISIONS = {
    "ON", "OPEN", "TEAM", "SO", "ALL", "NOW", "SEE", "IT", "BE", "GO",
    "AM", "IS", "WORK", "TARGET", "LOW", "GEO", "GIS", "KO", "DIS",
}


def norm_ep_num(fname_stem: str) -> int:
    m = re.match(r"EP(\d+)", fname_stem)
    return int(m.group(1)) if m else -1


def strip_audio_md(text: str) -> str:
    text = HEADER_RE.sub("", text, count=1)
    text = TS_RE.sub("", text)
    return text


def load_wmrs():
    data = json.loads(WMRS.read_text(encoding="utf-8"))
    return {rec["n"]: rec for rec in data}


def load_us_ticker_universe():
    """從 tickers.json 取得已知美股代號，並把「代號本身 + 名稱中的英文全稱」
    都當作同一家公司的『代稱集合』（surface forms），避免代號 vs 全稱寫法不同
    被誤判為聽錯。回傳 {symbol: {"company": 顯示名稱, "forms": set(...)}}。
    """
    tj = DATA / "tickers.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    universe = {}
    for sym, rec in d.items():
        if rec.get("market") != "US":
            continue
        if not (len(sym) >= 2 and re.fullmatch(r"[A-Z.]{2,6}", sym)):
            continue
        forms = set() if sym in COMMON_WORD_COLLISIONS else {sym}
        nm = (rec.get("name") or "").strip()
        if nm and re.search(r"[A-Za-z]{3,}", nm):
            for piece in re.findall(r"[A-Za-z][A-Za-z&.\-]{2,}(?:\s+[A-Z][A-Za-z&.\-]{2,})*", nm):
                if (piece.upper() not in ACRONYM_STOPWORDS
                        and piece.upper() not in COMMON_WORD_COLLISIONS
                        and len(piece) >= 3):
                    forms.add(piece)
        if not forms:
            continue
        universe[sym] = {"company": nm or sym, "forms": forms}
    return universe


def find_word(token: str, text: str):
    """回傳所有 word-boundary 命中位置。公司英文全稱大小寫常見不一致
    （如 NVIDIA vs Nvidia、CrowdStrike vs Crowdstrike），一律 case-insensitive。"""
    pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])", re.IGNORECASE)
    return [m.start() for m in pat.finditer(text)]


def context(text: str, pos: int, token: str, width=30):
    start = max(0, pos - width)
    end = min(len(text), pos + len(token) + width)
    return text[start:end].replace("\n", " ")


def locate_aligned_wmrs_window(audio_text, hit_pos, token, wmrs_text,
                                snip_width=150, min_match=10, win_width=150):
    """用音訊版命中點附近的中文上下文，在權威版全文裡找最長共同子字串當錨點，
    藉此定位「同一段話」在權威版對應的位置，避免用整篇全文比對造成誤判
    （wmrs 可能選擇性收錄，非逐字對照）。
    回傳 (aligned_window_text, match_size) 或 (None, 0) 表示定位不到對應段落。
    """
    start = max(0, hit_pos - snip_width)
    end = min(len(audio_text), hit_pos + len(token) + snip_width)
    snippet = audio_text[start:end]
    sm = difflib.SequenceMatcher(None, snippet, wmrs_text, autojunk=False)
    match = sm.find_longest_match(0, len(snippet), 0, len(wmrs_text))
    if match.size < min_match:
        return None, 0
    anchor = match.b + match.size // 2
    w_start = max(0, anchor - win_width)
    w_end = min(len(wmrs_text), anchor + win_width)
    return wmrs_text[w_start:w_end], match.size


def main():
    wmrs_by_n = load_wmrs()
    universe = load_us_ticker_universe()

    md_files = sorted(TRANSCRIPTS.glob("EP*.md"), key=lambda p: norm_ep_num(p.stem))

    report_lines = []
    total_eps = 0
    total_issues = 0
    high_confidence = []  # (ep, audio_token, analysis_symbol_hit, context)
    pending = []

    for fp in md_files:
        ep_num = norm_ep_num(fp.stem)
        if ep_num not in wmrs_by_n:
            continue  # 沒有權威版可比對，略過
        total_eps += 1
        ep_key = f"EP{ep_num}"

        audio_raw = fp.read_text(encoding="utf-8")
        audio_text = strip_audio_md(audio_raw)
        wmrs_text = wmrs_by_n[ep_num].get("tx", "")

        analysis_fp = ANALYSES / f"{ep_key}.json"
        analysis = None
        analysis_symbols = set()
        if analysis_fp.exists():
            analysis = json.loads(analysis_fp.read_text(encoding="utf-8"))
            for t in analysis.get("tickers") or []:
                if isinstance(t, dict):
                    s = (t.get("symbol") or "").strip().upper()
                    if s:
                        analysis_symbols.add(s)

        ep_issues = []

        # 以「公司」為單位比對：只要該公司任一代稱（代號或英文全稱）
        # 同時出現在音訊版與權威版，就視為同一家公司的合理寫法差異，不算疑點。
        # 只有音訊版提到、但權威版『完全沒有任何代稱』對應時，才是真正的疑點。
        for sym, info in universe.items():
            forms = info["forms"]
            audio_hit = None
            audio_hit_form = None
            for form in forms:
                hits = find_word(form, audio_text)
                if hits:
                    audio_hit = hits[0]
                    audio_hit_form = form
                    break
            if audio_hit is None:
                continue  # 音訊版根本沒提到這家公司

            wmrs_has_any_form = any(find_word(form, wmrs_text) for form in forms)
            if wmrs_has_any_form:
                continue  # 權威版也有對應（不論用代號或全稱），不算疑點

            ctx = context(audio_text, audio_hit, audio_hit_form)
            contaminated = sym in analysis_symbols

            # 用局部對齊找出權威版對應段落，檢查是否真的寫了「另一家公司」
            # （= 真正的聽錯證據），還是單純沒收錄該段落（= 無法判斷，非證據）
            aligned_window, match_size = locate_aligned_wmrs_window(
                audio_text, audio_hit, audio_hit_form, wmrs_text)

            substitute = None
            if aligned_window:
                for other_sym, other_info in universe.items():
                    if other_sym == sym:
                        continue
                    for form in other_info["forms"]:
                        if find_word(form, aligned_window):
                            substitute = (other_sym, other_info["company"], form)
                            break
                    if substitute:
                        break

            if substitute:
                align_status = "confirmed_substitute"  # 對齊到段落，且該段落寫了別家公司 → 強證據
            elif aligned_window:
                align_status = "aligned_no_mention"  # 對齊到段落，但該段落沒提到任何美股代號 → 弱證據
            else:
                align_status = "no_alignment"  # 完全定位不到對應段落（權威版可能未收錄）→ 非證據

            ep_issues.append({
                "type": "company",
                "token": audio_hit_form,
                "symbol": sym,
                "company": f"{sym}（{info['company']}）",
                "audio_context": ctx,
                "contaminated": contaminated,
                "align_status": align_status,
                "aligned_window": aligned_window,
                "substitute": substitute,
            })

        if not ep_issues:
            continue

        total_issues += len(ep_issues)
        report_lines.append(f"\n## {ep_key}（{wmrs_by_n[ep_num].get('d','')}）\n")
        for iss in ep_issues:
            flag = " ⚠️疑似污染分析" if iss["contaminated"] else ""
            align_note = {
                "confirmed_substitute": "✅對齊到段落，權威版該處寫的是另一家公司（強證據）",
                "aligned_no_mention": "△對齊到段落，但該處未提及任何美股代號（弱證據）",
                "no_alignment": "×定位不到對應段落，可能權威版未收錄（非證據）",
            }[iss["align_status"]]
            report_lines.append(
                f"- [{iss['type']}] 音訊版出現 `{iss['token']}`（{iss['company']}），"
                f"權威版逐字稿無對應{flag}\n"
                f"  - 對齊狀態：{align_note}\n"
                f"  - 音訊版上下文：「…{iss['audio_context']}…」\n"
            )
            if iss["substitute"]:
                osym, ocompany, oform = iss["substitute"]
                report_lines.append(f"  - 權威版對應段落提到：`{oform}`（{osym}／{ocompany}）\n")
            if iss["aligned_window"]:
                report_lines.append(f"  - 權威版對應段落：「…{iss['aligned_window'][:200].strip()}…」\n")
            entry = {
                "ep": ep_key, "date": wmrs_by_n[ep_num].get("d", ""),
                "type": iss["type"], "token": iss["token"], "symbol": iss["symbol"],
                "company": iss["company"], "context": iss["audio_context"],
                "contaminated": iss["contaminated"], "align_status": iss["align_status"],
                "substitute": iss["substitute"],
            }
            if iss["contaminated"]:
                high_confidence.append(entry)
            else:
                pending.append(entry)

    header = [
        "# 音訊逐字稿 vs 權威版逐字稿 — 差異審核報告\n",
        f"\n涵蓋集數：{total_eps}（音訊版與權威版逐字稿都存在的集數）\n",
        f"疑點總數：{total_issues}\n",
        f"疑似污染分析（高信心，可能需修正）：{len(high_confidence)}\n",
        f"待裁決（無法確定/未污染分析）：{len(pending)}\n",
        "\n---\n",
    ]

    OUT_MD.write_text("".join(header) + "".join(report_lines), encoding="utf-8")

    print(f"涵蓋集數: {total_eps}")
    print(f"疑點總數: {total_issues}")
    print(f"高信心(疑似污染分析): {len(high_confidence)}")
    print(f"待裁決: {len(pending)}")
    print()
    print("=== 高信心清單（污染分析）===")
    for e in high_confidence:
        print(e["ep"], e["token"], "->", e["company"], "|", e["align_status"],
              "| sub:", e["substitute"], "|", e["context"][:50])
    print()
    n_confirmed = sum(1 for e in pending if e["align_status"] == "confirmed_substitute")
    print(f"=== 待裁決清單中 align_status=confirmed_substitute 的（共 {n_confirmed} 筆，最值得人工複核） ===")
    for e in pending:
        if e["align_status"] == "confirmed_substitute":
            print(e["ep"], e["token"], "->", e["company"], "| sub:", e["substitute"], "|", e["context"][:50])


if __name__ == "__main__":
    main()
