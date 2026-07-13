#!/usr/bin/env python3
"""把逐字稿與結構化分析切成 RAG 可檢索的 chunk（JSONL），供之後建向量索引。

輸出（不進版控，見 .gitignore 的 data/rag/）：
  data/rag/transcript_chunks.jsonl — 逐字稿切塊，~700 字/塊、重疊 ~100 字，優先在句界切。
    同一集若 data/transcripts/EPxxx.md（自建逐字稿，有時間戳）存在就用它，否則用
    data/external/wmrs/transcripts.json 的 tx 欄位（無時間戳），兩者不重複。
  data/rag/analysis_chunks.jsonl — data/analyses/EPxxx.json 切塊，一個語意單位一塊
    （summary / market_view / industry / ticker / quote）。
  data/rag/extras_chunks.jsonl — data/extras/EPxxx.json 切塊，一個語意單位一塊
    （qa / chat / joke / wisdom / macro / ad）。extractor 批次仍在跑，讀檔逐檔
    try/except，壞檔/半寫檔跳過不中斷；之後重跑本腳本會自動補齊新完成的集數。

冪等：每次重跑整批覆寫三個輸出檔。
"""
import bisect
import json
import re

from common import ANALYSES, DATA, TRANSCRIPTS

WMRS_PATH = DATA / "external" / "wmrs" / "transcripts.json"
EXTRAS = DATA / "extras"
RAG_DIR = DATA / "rag"

CHUNK_TARGET = 700   # 目標字數/塊
CHUNK_OVERLAP = 100  # 相鄰塊重疊字數
BOUNDARY_CHARS = "。！？\n"  # 優先在這些字元後面切

TS_LINE_RE = re.compile(r"^\[(\d+:\d{2})\]\s*(.*)$")
OWN_FILE_RE = re.compile(r"^EP(\d+)\.md$")
# wmrs 較新一集的 tx 開頭常內嵌 "# EPxxx 標題\n\n"，切塊前先去掉，避免和 metadata 重複
WMRS_HEADER_RE = re.compile(r"^#\s*EP\d+[^\n]*\n+")


def load_wmrs():
    """讀 wmrs 逐字稿，回傳 {集數(int): 該集原始 record}。"""
    if not WMRS_PATH.exists():
        return {}
    records = json.loads(WMRS_PATH.read_text(encoding="utf-8"))
    return {r["n"]: r for r in records}


def find_own_transcripts():
    """回傳 {集數(int): Path}，掃 data/transcripts/EPxxx.md。"""
    result = {}
    for p in sorted(TRANSCRIPTS.glob("EP*.md")):
        m = OWN_FILE_RE.match(p.name)
        if m:
            result[int(m.group(1))] = p
    return result


def parse_own_transcript(path):
    """解析自建逐字稿（首行標題、之後每行 [mm:ss] 內容）。

    回傳 (full_text, offsets, timestamps)：
      full_text  — 各段落文字以 \n 接起來的全文
      offsets    — 各段落在 full_text 中的起始 char 位置（遞增）
      timestamps — 對應 offsets 的時間戳字串
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    segments = []  # [(timestamp, text)]
    for raw in lines[1:]:  # 跳過首行 "# EPxxx ｜ ... — 日期"
        line = raw.strip()
        if not line:
            continue
        m = TS_LINE_RE.match(line)
        if m:
            segments.append([m.group(1), m.group(2)])
        elif segments:
            segments[-1][1] += "\n" + line  # 無時間戳的續行，併入上一段

    parts, offsets, timestamps = [], [], []
    pos = 0
    for ts, text in segments:
        offsets.append(pos)
        timestamps.append(ts)
        parts.append(text)
        pos += len(text) + 1  # +1 對應 join 用的 "\n"
    return "\n".join(parts), offsets, timestamps


def timestamp_at(offsets, timestamps, pos):
    """回傳 offset <= pos 的最後一個時間戳（即該位置所在段落的時間戳）。"""
    if not offsets:
        return None
    i = bisect.bisect_right(offsets, pos) - 1
    return timestamps[i] if i >= 0 else None


def chunk_spans(text, target=CHUNK_TARGET, overlap=CHUNK_OVERLAP):
    """把文字切成 [start, end) 區間列表；優先在句界（。！？\\n）切，找不到就硬切。"""
    n = len(text)
    if n == 0:
        return []
    if n <= target:
        return [(0, n)]

    spans = []
    start = 0
    while start < n:
        tentative_end = min(start + target, n)
        if tentative_end >= n:
            spans.append((start, n))
            break
        end = tentative_end
        search_floor = max(start + target // 2, start + 1)
        for i in range(tentative_end, search_floor, -1):
            if text[i - 1] in BOUNDARY_CHARS:
                end = i
                break
        spans.append((start, end))
        new_start = end - overlap
        start = new_start if new_start > start else end
    return spans


def build_transcript_chunks():
    """組出 transcript_chunks.jsonl 的所有 record，並回傳 (chunks, 各來源集數統計)。"""
    wmrs_by_n = load_wmrs()
    own_files = find_own_transcripts()

    chunks = []
    ep_count = {"own": 0, "wmrs": 0}
    for n in sorted(wmrs_by_n):
        rec = wmrs_by_n[n]
        ep = f"EP{n}"
        title = rec.get("t", "")
        date = rec.get("d", "")

        if n in own_files:
            source = "own"
            full_text, offsets, timestamps = parse_own_transcript(own_files[n])
        else:
            source = "wmrs"
            tx = (rec.get("tx") or "")
            full_text = WMRS_HEADER_RE.sub("", tx, count=1)
            offsets, timestamps = [], []

        full_text = full_text.strip()
        if not full_text:
            continue

        for i, (s, e) in enumerate(chunk_spans(full_text)):
            text = full_text[s:e].strip()
            if not text:
                continue
            t_start = timestamp_at(offsets, timestamps, s) if source == "own" else None
            chunks.append({
                "id": f"{ep}-t{i + 1:04d}",
                "ep": ep,
                "date": date,
                "title": title,
                "source": source,
                "t_start": t_start,
                "industry": None,
                "stance": None,
                "category": None,
                "text": text,
            })
        ep_count[source] += 1

    return chunks, ep_count


def _unique_id(used, base):
    """避免同集同類型 id 撞名（例如同一集提到同一個標的兩次）。"""
    if base not in used:
        used.add(base)
        return base
    i = 2
    while f"{base}-{i}" in used:
        i += 1
    cand = f"{base}-{i}"
    used.add(cand)
    return cand


def build_analysis_chunks():
    """組出 analysis_chunks.jsonl 的所有 record，回傳 (chunks, 讀取檔數, 壞檔數)。"""
    chunks = []
    n_files = 0
    n_bad = 0
    for fp in sorted(ANALYSES.glob("EP*.json")):
        try:
            a = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            n_bad += 1  # NIM 回填程序正在同時寫這個目錄，壞檔（半寫入）直接跳過
            continue
        n_files += 1

        ep = a.get("ep_key") or fp.stem
        date = a.get("pubdate", "")
        used_ids = set()

        summary = (a.get("summary") or "").strip()
        if summary:
            chunks.append({
                "id": _unique_id(used_ids, f"{ep}-a-summary"),
                "ep": ep, "date": date, "type": "summary",
                "industry": None, "stance": None, "category": None,
                "text": f"{ep}（{date}）摘要：{summary}",
            })

        market_view = (a.get("market_view") or "").strip()
        if market_view:
            chunks.append({
                "id": _unique_id(used_ids, f"{ep}-a-market_view"),
                "ep": ep, "date": date, "type": "market_view",
                "industry": None, "stance": None, "category": None,
                "text": f"{ep}（{date}）大盤觀點：{market_view}",
            })

        for ind in a.get("industries") or []:
            if isinstance(ind, str):  # 模型偶爾輸出純字串而非物件
                ind = {"name": ind}
            name = (ind.get("name") or "").strip()
            if not name:
                continue
            slug = re.sub(r"[^\w一-鿿]+", "", name) or "ind"
            stance_raw = ind.get("stance")  # 原始立場字串（可能缺漏 → None）
            view = ind.get("view") or ""
            chunks.append({
                "id": _unique_id(used_ids, f"{ep}-a-industry-{slug}"),
                "ep": ep, "date": date, "type": "industry",
                "industry": name, "stance": stance_raw, "category": None,
                "text": f"{ep}（{date}）對產業「{name}」立場：{stance_raw or '?'}｜觀點：{view}",
            })

        for t in a.get("tickers") or []:
            if isinstance(t, str):
                t = {"symbol": t}
            symbol = (t.get("symbol") or t.get("name") or "").strip()
            if not symbol:
                continue
            name = t.get("name") or symbol
            stance_raw = t.get("stance")  # 原始立場字串（可能缺漏 → None）
            argument = t.get("argument") or ""
            chunks.append({
                "id": _unique_id(used_ids, f"{ep}-a-ticker-{symbol}"),
                "ep": ep, "date": date, "type": "ticker", "symbol": symbol,
                "industry": None, "stance": stance_raw, "category": None,
                "text": f"{ep}（{date}）對 {symbol}（{name}）立場：{stance_raw or '?'}｜論點：{argument}",
            })

        for i, q in enumerate(a.get("quotes") or []):
            quote = q.strip() if isinstance(q, str) else ""
            if not quote:
                continue
            chunks.append({
                "id": _unique_id(used_ids, f"{ep}-a-quote-{i + 1:02d}"),
                "ep": ep, "date": date, "type": "quote",
                "industry": None, "stance": None, "category": None,
                "text": quote,
            })

    return chunks, n_files, n_bad


def build_extras_chunks():
    """組出 extras_chunks.jsonl 的所有 record，回傳 (chunks, 讀取檔數, 壞檔數)。

    data/extras/EPxxx.json 是另一個抽取批次程序持續在寫的目錄，逐檔 try/except，
    壞檔/半寫檔跳過不中斷；下次重跑會自動補齊新完成的集數。
    """
    chunks = []
    n_files = 0
    n_bad = 0
    for fp in sorted(EXTRAS.glob("EP*.json")):
        try:
            a = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            n_bad += 1
            continue
        if not isinstance(a, dict):
            n_bad += 1
            continue
        n_files += 1

        ep = a.get("ep_key") or fp.stem
        date = a.get("date", "")
        title = a.get("title", "")
        counters = {}

        def add(kind, category, text):
            text = (text or "").strip()
            if not text:
                return
            counters[kind] = counters.get(kind, 0) + 1
            chunks.append({
                "id": f"{ep}-x-{kind}-{counters[kind]:02d}",
                "ep": ep, "date": date, "title": title, "type": kind,
                "category": category, "symbol": None, "industry": None,
                "stance": None, "t_start": None,
                "text": text,
            })

        for qa in a.get("qa") or []:
            if not isinstance(qa, dict):
                continue
            category = (qa.get("category") or "").strip() or None
            question = (qa.get("question") or "").strip()
            answer = (qa.get("answer_gist") or "").strip()
            if not question and not answer:
                continue
            add("qa", category, f"[{category or '其他'}] 問：{question}｜答：{answer}")

        for chat in a.get("chat") or []:
            if not isinstance(chat, dict):
                continue
            topic = (chat.get("topic") or "").strip() or None
            note = (chat.get("note") or "").strip()
            if not note:
                continue
            add("chat", topic, f"{topic or '閒聊'}：{note}")

        for joke in a.get("jokes") or []:
            if isinstance(joke, str):
                add("joke", None, joke)

        for wisdom in a.get("wisdom") or []:
            if isinstance(wisdom, str):
                add("wisdom", None, wisdom)

        for macro in a.get("macro") or []:
            if not isinstance(macro, dict):
                continue
            topic = (macro.get("topic") or "").strip() or None
            view = (macro.get("view") or "").strip()
            if not view:
                continue
            add("macro", topic, f"{topic or '宏觀'}：{view}")

        # ads 不進 RAG（2026-07-14 使用者指示：整理時去除所有業配）；
        # 原始 sponsor 紀錄仍在 data/extras/ 備查

    return chunks, n_files, n_bad


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    RAG_DIR.mkdir(parents=True, exist_ok=True)

    t_chunks, ep_count = build_transcript_chunks()
    a_chunks, n_files, n_bad = build_analysis_chunks()
    x_chunks, xn_files, xn_bad = build_extras_chunks()

    t_path = RAG_DIR / "transcript_chunks.jsonl"
    a_path = RAG_DIR / "analysis_chunks.jsonl"
    x_path = RAG_DIR / "extras_chunks.jsonl"
    write_jsonl(t_path, t_chunks)
    write_jsonl(a_path, a_chunks)
    write_jsonl(x_path, x_chunks)

    t_chars = sum(len(c["text"]) for c in t_chunks)
    a_chars = sum(len(c["text"]) for c in a_chunks)
    x_chars = sum(len(c["text"]) for c in x_chunks)

    print(f"逐字稿來源集數：own {ep_count['own']} 集、wmrs {ep_count['wmrs']} 集")
    print(f"{t_path.name}：{len(t_chunks)} 塊，總字元數 {t_chars}")
    print(f"{a_path.name}：讀取 {n_files} 檔（壞檔跳過 {n_bad}），{len(a_chunks)} 塊，總字元數 {a_chars}")
    print(f"{x_path.name}：讀取 {xn_files} 檔（壞檔跳過 {xn_bad}），{len(x_chunks)} 塊，總字元數 {x_chars}")


if __name__ == "__main__":
    main()
