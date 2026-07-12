#!/usr/bin/env python3
"""把 data/analyses/*.json 彙整成標的與產業的立場時間軸。

輸出 data/tickers.json：
  {symbol: {name, market, mentions, latest_stance, latest_date,
            timeline: [{ep, date, stance, argument}]}}
輸出 data/industries.json 同構。
"""
import json
import re

from common import ANALYSES, DATA


def norm_symbol(t):
    """統一代號：台股數字、美股大寫；公司名原樣。"""
    s = (t.get("symbol") or t.get("name") or "").strip().upper()
    s = re.sub(r"^[$]", "", s)
    m = re.match(r"^(\d{4,6})", s)  # "2330.TW" / "2330 台積電" → 2330
    if m:
        return m.group(1)
    return s


def main():
    tickers, industries = {}, {}
    files = sorted(ANALYSES.glob("EP*.json")) + sorted(ANALYSES.glob("SP-*.json"))
    for fp in files:
        a = json.loads(fp.read_text(encoding="utf-8"))
        ep, date = a["ep_key"], a["pubdate"]
        for t in a.get("tickers") or []:
            if isinstance(t, str):  # 模型偶爾輸出純字串而非物件
                t = {"symbol": t}
            sym = norm_symbol(t)
            if not sym:
                continue
            rec = tickers.setdefault(sym, {
                "name": t.get("name") or sym, "market": t.get("market") or "?",
                "timeline": []})
            rec["timeline"].append({"ep": ep, "date": date,
                                    "stance": t.get("stance") or "?",
                                    "argument": t.get("argument") or ""})
        for ind in a.get("industries") or []:
            if isinstance(ind, str):  # 模型偶爾輸出純字串而非物件
                ind = {"name": ind}
            name = (ind.get("name") or "").strip()
            if not name:
                continue
            rec = industries.setdefault(name, {"timeline": []})
            rec["timeline"].append({"ep": ep, "date": date,
                                    "stance": ind.get("stance") or "?",
                                    "view": ind.get("view") or ""})

    for rec in list(tickers.values()) + list(industries.values()):
        rec["timeline"].sort(key=lambda x: x["date"], reverse=True)
        rec["mentions"] = len(rec["timeline"])
        rec["latest_stance"] = rec["timeline"][0]["stance"]
        rec["latest_date"] = rec["timeline"][0]["date"]

    (DATA / "tickers.json").write_text(
        json.dumps(tickers, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "industries.json").write_text(
        json.dumps(industries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"彙整 {len(files)} 集 → {len(tickers)} 檔標的、{len(industries)} 個產業")


if __name__ == "__main__":
    main()
