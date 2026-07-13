#!/usr/bin/env python3
"""套用人工審查後的美股代號修正清單（延續 _audit_us_symbols.py 的自動修正）。
執行一次即可；修正清單來自人工讀逐字稿 + 資料庫內部一致性比對（同公司在其他集
已有正確代號可佐證）+ WebSearch 驗證冷門公司真實代號。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANALYSES = ROOT / "data" / "analyses"

# (ep_key, old_symbol) -> (new_symbol, new_name, evidence)
FIXES = {
    ("EP362", "AOI"): ("AAOI", "Applied Optoelectronics",
        "逐字稿：'AOI 它處分掉中國的廠房，然後跑去美國設廠，然後在微軟的協助之下' "
        "= AAOI 2023年出售中國廠房+微軟供應協議實況，原name'Alpha and Omega Semiconductor'誤植"),
    ("EP507", "AOI"): ("AAOI", "Applied Optoelectronics",
        "逐字稿：'AOI 為光通廠，市場預期高' + industries含'光通訊'觀察，AOI為孤兒代號應為AAOI"),
    ("EP642", "ALTR"): ("ALAB", "Astera Labs",
        "name欄位已是'Astera Labs'，與資料庫另13集ALAB/Astera Labs記錄一致；"
        "ALTR為Altair Engineering真實代號，非本公司"),
    ("EP500", "Qualcomm"): ("QCOM", "Qualcomm", "symbol欄位誤填公司全名，真實代號QCOM"),
    ("EP500", "Broadcom"): ("AVGO", "Broadcom", "symbol欄位誤填公司全名，真實代號AVGO"),
    ("EP500", "Microsoft"): ("MSFT", "Microsoft", "symbol欄位誤填公司全名，真實代號MSFT"),
    ("EP512", "Impinj"): ("PI", "Impinj",
        "逐字稿提及Impinj RFID晶片公司；symbol欄位誤填公司全名，真實代號PI"),
    ("EP513", "Adobe"): ("ADBE", "Adobe",
        "逐字稿提及Adobe Text2Video；symbol欄位誤填公司全名，真實代號ADBE"),
    ("EP537", "CoreWeave"): ("CRWV", "CoreWeave",
        "逐字稿提及CoreWeave與NVIDIA投資關係；symbol欄位誤填公司全名，真實代號CRWV"),
    ("EP560", "Amphenol"): ("APH", "Amphenol", "symbol欄位誤填公司全名，真實代號APH"),
    ("EP560", "Rogers"): ("ROG", "Rogers Corporation",
        "Midplane材料供應商語境，Rogers Corporation真實代號ROG（非Rogers Communications）"),
    ("EP563", "CoreWeave"): ("CRWV", "CoreWeave",
        "逐字稿提及CoreWeave上市；symbol欄位誤填公司全名，真實代號CRWV"),
    ("EP597", "Sony"): ("SONY", "Sony", "資料庫其他集已有SONY正確記錄，symbol欄位誤填公司全名"),
    ("EP623", "Tesla"): ("TSLA", "Tesla", "symbol欄位誤填公司全名，真實代號TSLA"),
    ("EP623", "Amphenol"): ("APH", "Amphenol", "symbol欄位誤填公司全名，真實代號APH"),
    ("EP623", "Credo"): ("CRDO", "Credo",
        "argument描述'銅線傳輸相關標的'精準對應Credo Technology主業，symbol應為CRDO"),
    ("EP629", "Ryanair"): ("RYAAY", "Ryanair Holdings",
        "Ryanair美股ADR真實代號RYAAY（Nasdaq）"),
    ("EP631", "Tesla"): ("TSLA", "Tesla", "symbol欄位誤填公司全名，真實代號TSLA"),
    ("EP664", "Google"): ("GOOGL", "Google",
        "逐字稿提及Google TPU Cluster；資料庫慣例多用GOOGL(59次)，symbol誤填公司全名"),
    ("EP664", "Intel"): ("INTC", "Intel", "symbol欄位誤填公司全名，真實代號INTC"),
    ("EP665", "VISHAY"): ("VSH", "Vishay",
        "逐字稿：'你看一下 Vishay，你看一下 VPG'，真實代號VSH（VISHAY非標準代號格式）"),
    ("EP666", "美光"): ("MU", "美光", "symbol欄位誤填中文公司名，真實代號MU"),
    ("EP668", "Adobe"): ("ADBE", "Adobe",
        "逐字稿提及Adobe AI改圖爭議；symbol欄位誤填公司全名，真實代號ADBE"),
    ("EP670", "Nvidia"): ("NVDA", "Nvidia", "symbol欄位誤填公司全名，真實代號NVDA"),
    ("EP670", "Palantir"): ("PLTR", "Palantir",
        "逐字稿提及Palantir CEO Alex Karp；symbol欄位誤填公司全名，真實代號PLTR"),
    ("EP671", "Texas Instruments"): ("TXN", "Texas Instruments",
        "逐字稿提及Texas Instruments加單傳言；symbol欄位誤填公司全名，真實代號TXN"),
    ("EP672", "德州儀器"): ("TXN", "德州儀器",
        "逐字稿提及'TI、ST、安森美(onsemi)'，TI=Texas Instruments真實代號TXN"),
    ("EP672", "安森美"): ("ON", "安森美",
        "逐字稿提及'安森美（onsemi)'；symbol欄位誤填中文公司名，真實代號ON"),
    ("EP677", "Tesla"): ("TSLA", "Tesla", "symbol欄位誤填公司全名，真實代號TSLA"),
    ("EP83", "Zillow"): ("Z", "Zillow", "symbol欄位誤填公司全名，真實代號Z（Class C；Class A為ZG）"),
    ("EP83", "Opendoor"): ("OPEN", "Opendoor", "symbol欄位誤填公司全名，真實代號OPEN"),
    ("EP83", "Redfin"): ("RDFN", "Redfin", "symbol欄位誤填公司全名，真實代號RDFN"),
    ("EP496", "TSLA 2x ETF"): ("TSLL", "兩倍特斯拉",
        "WebSearch確認：Direxion Daily TSLA Bull 2X Shares於2022-08-09上市，真實代號TSLL"),
    ("EP45", "FANGDD"): ("DUO", "房多多",
        "WebSearch確認：Fangdd Network Group Ltd. 在Nasdaq真實代號為DUO，非公司名縮寫"),
    ("EP169", "NXP"): ("NXPI", "恩智浦半導體",
        "資料庫EP104已有正確NXPI/恩智浦半導體記錄；NXP非真實代號格式，真實代號NXPI"),
    ("EP196", "NXP"): ("NXPI", "恩智浦半導體", "同上，真實代號NXPI"),
    ("EP474", "NXP"): ("NXPI", "恩智浦半導體", "同上，真實代號NXPI"),
    ("EP584", "ALST"): ("CLS", "Celestica",
        "argument'作為Google的主要組裝廠'與資料庫其他13集CLS/Celestica記錄完全一致，ALST非真實代號"),
    ("EP175", "GSTAT"): ("GSAT", "Globalstar",
        "資料庫EP278已有正確GSAT/Globalstar記錄；GSTAT非真實代號，真實代號GSAT"),
    ("EP618", "LUMN"): ("LITE", "Lumentum",
        "argument'Google OCS交換器方案'為Lumentum光通訊/MEMS業務，LUMN實為Lumen Technologies(電信業，無關)真實代號，本公司真實代號應為LITE"),
    ("EP620", "LUMN"): ("LITE", "Lumentum", "argument'美股光通訊指標股'，同上判斷，真實代號LITE"),
    ("EP634", "LUMN"): ("LITE", "Lumentum", "argument'Google OCS所需MEMS解決方案'，同上判斷，真實代號LITE"),
    ("EP642", "LUMN"): ("LITE", "Lumentum", "argument'光通訊強勢股'，同上判斷，真實代號LITE"),
    ("EP122", "CDPR"): ("CDR", "CD Projekt",
        "資料庫EP134已有正確CDR記錄（CD Projekt於Warsaw證交所真實代號CDR）；CDPR非真實代號"),
    ("EP171", "LVMH"): ("LVMUY", "LVMH",
        "資料庫EP90已有正確LVMUY記錄（LVMH美股OTC ADR真實代號）；'LVMH'本身非任何交易所真實代號"),
    ("EP641", "LUMN"): ("LITE", "Lumentum",
        "argument'在美股光通訊佈局中，屬於看得到客戶與出貨量的確定性標的'=Lumentum光通訊業務，"
        "LUMN實為Lumen Technologies(電信業，無關)真實代號，真實代號應為LITE（第二輪fuzzy比對補漏）"),
    ("EP449", "NXP"): ("NXPI", "恩智浦",
        "資料庫另4集(EP104/169/196/474)已有正確NXPI記錄；NXP非真實代號格式，真實代號NXPI（第二輪fuzzy比對補漏）"),
    ("EP328", "IFX"): ("IFNNY", "Infineon",
        "IFX為Infineon法蘭克福證交所代號；market欄位標US，資料庫EP135已有正確美股OTC ADR代號IFNNY，"
        "本集market既標US故統一為IFNNY（第二輪fuzzy比對補漏）"),
}

# name-only fix (symbol 保持不變，只修正被誤植的公司名)
NAME_ONLY_FIXES = {
    ("EP670", "FLY"): ("Firefly Aerospace",
        "逐字稿：'RKLB、ASTS 或是 Fly，就是這些跟衛星或是通訊有關係的股票'，"
        "WebSearch確認FLY為Firefly Aerospace(2025-08上市)真實代號，非Flywire(支付公司)"),
}


def main():
    applied = []
    for (ep, old_sym), (new_sym, new_name, evidence) in FIXES.items():
        fp = ANALYSES / f"{ep}.json"
        a = json.loads(fp.read_text(encoding="utf-8"))
        changed = False
        for t in a.get("tickers") or []:
            if isinstance(t, dict) and (t.get("symbol") or "").strip() == old_sym:
                old_name = t.get("name")
                t["symbol"] = new_sym
                t["name"] = new_name
                changed = True
                applied.append({
                    "ep": ep, "old_symbol": old_sym, "new_symbol": new_sym,
                    "old_name": old_name, "new_name": new_name, "evidence": evidence,
                })
        if changed:
            fp.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")

    for (ep, sym), (new_name, evidence) in NAME_ONLY_FIXES.items():
        fp = ANALYSES / f"{ep}.json"
        a = json.loads(fp.read_text(encoding="utf-8"))
        changed = False
        for t in a.get("tickers") or []:
            if isinstance(t, dict) and (t.get("symbol") or "").strip() == sym:
                old_name = t.get("name")
                t["name"] = new_name
                changed = True
                applied.append({
                    "ep": ep, "old_symbol": sym, "new_symbol": sym,
                    "old_name": old_name, "new_name": new_name, "evidence": evidence,
                })
        if changed:
            fp.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"套用修正 {len(applied)} 筆")
    out = ROOT / "data" / "_audit_manual_fixes.json"
    out.write_text(json.dumps(applied, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
