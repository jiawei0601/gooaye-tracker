#!/usr/bin/env python3
"""建 RAG 本機索引：讀 data/rag/*.jsonl → data/rag/gooaye.db。

只用標準庫（sqlite3 + urllib）。內容：
  chunks       — 逐字稿塊 + 分析塊的統一表，含 ep/date/kind/symbol/industry/stance 等欄位。
  chunks_fts   — FTS5 虛擬表（tokenize='trigram'），對 text 做全文/子字串檢索。
  embeddings   — NIM embedding 向量（float16 bytes），id 對應 chunks.id。
  meta         — 記錄選定的 embedding 模型名/維度/input_type 模式。

冪等：
  - chunks 每次全量 upsert（INSERT OR REPLACE，來源 JSONL 覆寫即可反映最新內容）。
  - chunks_fts 每次全量重建（成本低，資料量小）。
  - embeddings 只補「還沒有向量的 id」；已选定的模型記在 meta，不重新探測。

NIM 全部候選模型都不可用時：印出說明並保留純 FTS5 版（不中斷、不無限重試）。
"""
import json
import os
import re
import sqlite3
import struct
import sys
import time
import urllib.error
import urllib.request

from common import DATA, load_env

RAG_DIR = DATA / "rag"
DB_PATH = RAG_DIR / "gooaye.db"
TRANSCRIPT_JSONL = RAG_DIR / "transcript_chunks.jsonl"
ANALYSIS_JSONL = RAG_DIR / "analysis_chunks.jsonl"

NIM_URL = "https://integrate.api.nvidia.com/v1/embeddings"
# (model, 是否需要 input_type 參數)；依序試，第一個能用的就採用。
CANDIDATE_MODELS = [
    ("baai/bge-m3", False),
    ("nvidia/llama-3.2-nv-embedqa-1b-v2", True),
    ("nvidia/nv-embedqa-e5-v5", True),
]
BATCH_SIZE = 48
MAX_RETRIES = 3
MAX_CONSEC_FAIL_BATCHES = 10

EP_NUM_RE = re.compile(r"^EP(\d+)")


def ep_num_of(ep):
    m = EP_NUM_RE.match(ep or "")
    return int(m.group(1)) if m else None


def load_jsonl(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def to_chunk_row(rec, default_kind=None):
    kind = rec.get("type") or default_kind
    return (
        rec["id"],
        rec.get("ep"),
        ep_num_of(rec.get("ep")),
        rec.get("date"),
        kind,
        rec.get("symbol"),
        rec.get("industry"),
        rec.get("stance"),
        rec.get("t_start"),
        rec.get("source"),
        rec.get("text"),
    )


def ensure_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            ep TEXT,
            ep_num INTEGER,
            date TEXT,
            kind TEXT,
            symbol TEXT,
            industry TEXT,
            stance TEXT,
            t_start TEXT,
            source TEXT,
            text TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id TEXT PRIMARY KEY,
            vec BLOB
        )
    """)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()


def upsert_chunks(conn):
    t_recs = load_jsonl(TRANSCRIPT_JSONL)
    a_recs = load_jsonl(ANALYSIS_JSONL)
    rows = [to_chunk_row(r, default_kind="transcript") for r in t_recs]
    rows += [to_chunk_row(r) for r in a_recs]
    conn.executemany(
        "INSERT OR REPLACE INTO chunks "
        "(id, ep, ep_num, date, kind, symbol, industry, stance, t_start, source, text) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return len(rows)


def rebuild_fts(conn):
    conn.execute("DROP TABLE IF EXISTS chunks_fts")
    conn.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(id UNINDEXED, text, tokenize='trigram')")
    conn.execute("INSERT INTO chunks_fts (id, text) SELECT id, text FROM chunks")
    conn.commit()


def _post(model, texts, input_type):
    payload = {"input": texts, "model": model}
    if input_type:
        payload["input_type"] = input_type
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        NIM_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {os.environ['NVIDIA_NIM_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def embed_batch(model, needs_input_type, texts, input_type="passage"):
    """呼叫 NIM 拿 texts 的 embedding（依原順序回傳）。429/5xx/連線錯 重試 3 次，其他錯直接丟出。"""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            body = _post(model, texts, input_type if needs_input_type else None)
            data = body.get("data")
            if not data:
                raise RuntimeError(f"NIM 回應無 data：{body}")
            data = sorted(data, key=lambda d: d["index"])
            return [d["embedding"] for d in data]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            time.sleep(2 ** attempt)
            continue
    raise RuntimeError(f"{model} 連續 {MAX_RETRIES} 次失敗：{last_err}")


def probe_model():
    """依序試候選模型，回傳 (model, needs_input_type, dim)；全部失敗回 None。"""
    test_texts = ["台積電今天大漲，法人買超", "半導體產業展望轉趨保守"]
    for model, needs_input_type in CANDIDATE_MODELS:
        try:
            vecs = embed_batch(model, needs_input_type, test_texts)
            dim = len(vecs[0])
            print(f"探測 {model}：可用，維度 {dim}")
            return model, needs_input_type, dim
        except Exception as e:
            print(f"探測 {model}：不可用（{e}）")
    return None


def build_embeddings(conn):
    load_env()
    if not os.environ.get("NVIDIA_NIM_API_KEY"):
        print("未設定 NVIDIA_NIM_API_KEY，略過 embedding，交付純 FTS5 版。")
        return

    row = conn.execute("SELECT value FROM meta WHERE key='model'").fetchone()
    if row:
        model = row[0]
        mode_row = conn.execute("SELECT value FROM meta WHERE key='input_type_mode'").fetchone()
        needs_input_type = bool(mode_row and mode_row[0] == "passage_query")
        dim = int(conn.execute("SELECT value FROM meta WHERE key='dim'").fetchone()[0])
        print(f"沿用既有模型設定：{model}（維度 {dim}）")
    else:
        probed = probe_model()
        if not probed:
            print("所有候選 NIM embedding 模型皆不可用（今天可能故障中），交付純 FTS5 版，不建向量索引。")
            return
        model, needs_input_type, dim = probed
        conn.executemany(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            [
                ("model", model),
                ("dim", str(dim)),
                ("input_type_mode", "passage_query" if needs_input_type else "none"),
            ],
        )
        conn.commit()

    rows = conn.execute(
        "SELECT c.id, c.text FROM chunks c LEFT JOIN embeddings e ON c.id = e.id WHERE e.id IS NULL"
    ).fetchall()
    total = len(rows)
    print(f"待補向量：{total} 筆")
    if total == 0:
        return

    consec_fail = 0
    done = 0
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    for bi in range(n_batches):
        batch = rows[bi * BATCH_SIZE:(bi + 1) * BATCH_SIZE]
        ids = [r[0] for r in batch]
        texts = [r[1] for r in batch]
        try:
            vecs = embed_batch(model, needs_input_type, texts, input_type="passage")
            payload = [(cid, struct.pack(f"<{dim}e", *v)) for cid, v in zip(ids, vecs)]
            conn.executemany("INSERT OR REPLACE INTO embeddings (id, vec) VALUES (?, ?)", payload)
            conn.commit()
            done += len(batch)
            consec_fail = 0
            if bi % 10 == 0 or bi == n_batches - 1:
                print(f"embedding 進度：{done}/{total}（批次 {bi + 1}/{n_batches}）")
        except Exception as e:
            consec_fail += 1
            print(f"批次 {bi + 1}/{n_batches} 失敗：{e}")
            if consec_fail >= MAX_CONSEC_FAIL_BATCHES:
                print(
                    f"連續 {MAX_CONSEC_FAIL_BATCHES} 批失敗，停止（已完成 {done}/{total}）。"
                    "關鍵字（FTS5）功能不受影響，之後重跑本腳本可續跑缺的向量。"
                )
                break


def main():
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)

    n = upsert_chunks(conn)
    print(f"chunks 表：upsert {n} 筆")

    rebuild_fts(conn)
    fts_cnt = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    print(f"chunks_fts 重建完成：{fts_cnt} 筆")

    build_embeddings(conn)

    emb_cnt = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    total_cnt = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"embeddings：{emb_cnt}/{total_cnt}")
    conn.close()


if __name__ == "__main__":
    main()
