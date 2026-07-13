#!/usr/bin/env python3
"""一次性稽核腳本：比對 data/analyses/*.json 的美股 ticker symbol 是否與
data/external/wmrs/transcripts.json 逐字稿內容吻合，抓出誤植/孤兒代號。

輸出：
- data/audit_us_symbols.md（審計報告）
- 印出統計摘要
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANALYSES = ROOT / "data" / "analyses"
WMRS = ROOT / "data" / "external" / "wmrs" / "transcripts.json"
REPORT = ROOT / "data" / "audit_us_symbols.md"

# 已知混淆對照：記錄的 symbol（誤） -> (正確 symbol, 正確公司名, 判斷用公司名關鍵字)
# 用於在逐字稿裡尋找「公司名證據」時輔助比對。
KNOWN_CONFUSIONS = {
    "ASTS": {"correct": "ALAB", "correct_name": "Astera Labs", "wrong_name": "AST SpaceMobile"},
    "AOI": {"correct": "AAOI", "correct_name": "Applied Optoelectronics", "wrong_name": None},
}

# 公司名 -> 正確代號 對照表（先驗知識，仍需逐字稿佐證再判定）
NAME_TO_SYMBOL = {
    "astera labs": "ALAB",
    "ast spacemobile": "ASTS",
    "applied optoelectronics": "AAOI",
    "credo": "CRDO",
    "lumentum": "LITE",
    "coherent": "COHR",
    "nebius": "NBIS",
    "celestica": "CLS",
    "vertiv": "VRT",
    "arista": "ANET",
    "vistra": "VST",
    "constellation energy": "CEG",
    "talen": "TLN",
    "nuscale": "SMR",
    "unity": "U",
    "cloudflare": "NET",
}

def load_wmrs():
    data = json.loads(WMRS.read_text(encoding="utf-8"))
    by_n = {}
    for rec in data:
        by_n[rec["n"]] = rec
    return by_n


def is_us_ticker(t):
    if not isinstance(t, dict):
        return False
    market = (t.get("market") or "").strip().upper()
    sym = (t.get("symbol") or "").strip()
    if market == "US":
        return True
    if market == "" and sym.isalpha() and sym.isupper() and 1 <= len(sym) <= 5:
        return True
    return False


def find_evidence(tx, symbol, name):
    """在逐字稿中找 symbol 或公司名的證據片段，回傳 (found, snippet)。"""
    if not tx:
        return False, ""
    snippets = []
    # 1) 直接找 symbol 字串（避免太短代號誤配，如 U/NET 等常見詞，做寬鬆處理）
    if symbol and len(symbol) >= 3:
        idx = tx.find(symbol)
        if idx >= 0:
            snippets.append(tx[max(0, idx - 15):idx + 25])
    # 2) 找公司名（name 欄位）
    if name:
        idx = tx.find(name)
        if idx >= 0:
            snippets.append(tx[max(0, idx - 15):idx + 25])
    return (len(snippets) > 0), " | ".join(s.replace("\n", " ") for s in snippets[:2])[:120]


def main():
    wmrs = load_wmrs()
    files = sorted(ANALYSES.glob("EP*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))

    total_us = 0
    confirmed_ok = 0
    fixed = []       # list of dict: ep, old_symbol, new_symbol, old_name, new_name, evidence
    suspicious = []  # list of dict: ep, symbol, name, reason, evidence

    for fp in files:
        a = json.loads(fp.read_text(encoding="utf-8"))
        ep_key = a.get("ep_key") or fp.stem
        m = re.match(r"EP(\d+)", ep_key)
        if not m:
            continue
        n = int(m.group(1))
        wrec = wmrs.get(n)
        tx = wrec.get("tx", "") if wrec else ""

        tickers = a.get("tickers") or []
        changed = False
        for t in tickers:
            if not isinstance(t, dict):
                continue  # 跳過已知的扁平陣列schema怪異案例(EP565)，不在本次範圍
            if not is_us_ticker(t):
                continue
            total_us += 1
            symbol = (t.get("symbol") or "").strip()
            name = (t.get("name") or "").strip()

            # 情況 A：已知混淆表命中
            conf = KNOWN_CONFUSIONS.get(symbol)
            if conf:
                found, snippet = find_evidence(tx, symbol, conf["correct_name"])
                # 用 correct_name 去找證據（例如逐字稿提到 Astera Labs / Astera）
                name_hit = conf["correct_name"].split()[0] in tx or conf["correct_name"] in tx
                if name_hit or name.strip() == conf["correct_name"]:
                    old_symbol, old_name = symbol, name
                    t["symbol"] = conf["correct"]
                    t["name"] = conf["correct_name"]
                    fixed.append({
                        "ep": ep_key, "old_symbol": old_symbol, "new_symbol": conf["correct"],
                        "old_name": old_name, "new_name": conf["correct_name"],
                        "evidence": snippet or f"name欄位='{old_name}'，先驗對照表判定",
                    })
                    changed = True
                    continue
                else:
                    suspicious.append({
                        "ep": ep_key, "symbol": symbol, "name": name,
                        "reason": f"命中已知混淆表({symbol}->{conf['correct']})但逐字稿找不到公司名證據",
                        "evidence": "",
                    })
                    continue

            # 情況 B：name 欄位本身等於代號（孤兒代號，如 AOI name='AOI'）
            if name.upper() == symbol.upper() and symbol in NAME_TO_SYMBOL_REVERSE_HINT(symbol):
                pass  # 已由已知混淆表處理，這裡不會走到

            # 情況 C：一般驗證 —— symbol 或 name 是否能在逐字稿找到證據
            found, snippet = find_evidence(tx, symbol, name)
            if found:
                confirmed_ok += 1
                continue
            else:
                # 找不到任何證據 → 列入可疑待裁
                suspicious.append({
                    "ep": ep_key, "symbol": symbol, "name": name,
                    "reason": "逐字稿找不到 symbol 或公司名證據（可能無逐字稿/口語未提及/代號有誤）",
                    "evidence": "",
                })

        if changed:
            fp.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")

    write_report(total_us, confirmed_ok, fixed, suspicious)
    print(f"掃描美股ticker筆數: {total_us}")
    print(f"確認正確: {confirmed_ok}")
    print(f"修正: {len(fixed)}")
    print(f"待裁決(可疑): {len(suspicious)}")


def NAME_TO_SYMBOL_REVERSE_HINT(symbol):
    return []


def write_report(total_us, confirmed_ok, fixed, suspicious):
    lines = []
    lines.append("# 美股代號誤植審計報告\n")
    lines.append(f"- 掃描美股 ticker 筆數：{total_us}")
    lines.append(f"- 確認正確：{confirmed_ok}")
    lines.append(f"- 修正（高信心）：{len(fixed)}")
    lines.append(f"- 待使用者裁決（可疑）：{len(suspicious)}\n")

    lines.append("## 修正清單\n")
    if fixed:
        lines.append("| EP | 原symbol | 新symbol | 原name | 新name | 逐字稿證據 |")
        lines.append("|---|---|---|---|---|---|")
        for f in fixed:
            lines.append(
                f"| {f['ep']} | {f['old_symbol']} | {f['new_symbol']} | "
                f"{f['old_name']} | {f['new_name']} | {f['evidence']} |"
            )
    else:
        lines.append("（無）")
    lines.append("")

    lines.append("## 待使用者裁決（可疑，未動）\n")
    if suspicious:
        lines.append("| EP | symbol | name | 原因 |")
        lines.append("|---|---|---|---|")
        for s in suspicious:
            lines.append(f"| {s['ep']} | {s['symbol']} | {s['name']} | {s['reason']} |")
    else:
        lines.append("（無）")
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
