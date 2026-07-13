#!/usr/bin/env python3
"""查詢 data/rag/gooaye.db 的 CLI 工具。

用法：
  python scripts/rag_query.py --q "台積電漲價" --mode keyword
  python scripts/rag_query.py --symbol 2330 --kind ticker
  python scripts/rag_query.py --since 2024-01-01 --until 2024-06-30 --industry 半導體

模式（--mode）：
  keyword  — FTS5（trigram）子字串檢索。
  semantic — NIM embedding 餘弦相似度（無向量時自動降級 keyword 並提示）。
  hybrid   — 兩者用 reciprocal rank fusion 合併（預設）。
無 --q 時純過濾瀏覽，按日期倒序。
"""
import argparse
import math
import re
import sqlite3
import struct
import sys

from common import DATA
from rag_build_index import embed_batch

DB_PATH = DATA / "rag" / "gooaye.db"


def parse_args():
    p = argparse.ArgumentParser(description="查詢 gooaye RAG 索引")
    p.add_argument("--q", default=None, help="查詢文字")
    p.add_argument("--since", default=None, help="起始日期 YYYY-MM-DD（含）")
    p.add_argument("--until", default=None, help="結束日期 YYYY-MM-DD（含）")
    p.add_argument("--ep", default=None, help="集數，如 160 或 EP160")
    p.add_argument("--symbol", default=None, help="標的代碼（精確比對，不分大小寫）")
    p.add_argument("--industry", default=None, help="產業名（子字串）")
    p.add_argument("--stance", default=None, help="立場（精確比對，如 看多/看空/中性）")
    p.add_argument(
        "--kind", default=None,
        choices=["transcript", "summary", "market_view", "ticker", "industry", "quote"],
        help="塊類型",
    )
    p.add_argument("--k", type=int, default=10, help="回傳筆數，預設 10")
    p.add_argument("--mode", default="hybrid", choices=["keyword", "semantic", "hybrid"])
    return p.parse_args()


def normalize_ep(ep):
    if ep is None:
        return None
    ep = ep.strip()
    if re.match(r"^\d+$", ep):
        return f"EP{ep}"
    return ep


def build_filters(args):
    """回傳 (where_sql, params) 對應 chunks 表別名 c。"""
    clauses = []
    params = []
    if args.since:
        clauses.append("c.date >= ?")
        params.append(args.since)
    if args.until:
        clauses.append("c.date <= ?")
        params.append(args.until)
    ep = normalize_ep(args.ep)
    if ep:
        clauses.append("c.ep = ?")
        params.append(ep)
    if args.symbol:
        clauses.append("UPPER(c.symbol) = UPPER(?)")
        params.append(args.symbol)
    if args.industry:
        clauses.append("c.industry LIKE ?")
        params.append(f"%{args.industry}%")
    if args.stance:
        clauses.append("c.stance = ?")
        params.append(args.stance)
    if args.kind:
        clauses.append("c.kind = ?")
        params.append(args.kind)
    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


def fetch_filtered(conn, args, extra_where="", extra_params=(), order="c.date DESC", limit=None):
    where, params = build_filters(args)
    sql = (
        "SELECT c.id, c.ep, c.date, c.kind, c.symbol, c.industry, c.stance, c.t_start, c.text "
        "FROM chunks c WHERE 1=1" + where + extra_where + f" ORDER BY {order}"
    )
    params = params + list(extra_params)
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def _like_search(conn, args, terms, limit):
    """LIKE 全表掃描後備（33k 列可接受）：所有 terms 都要出現（AND），沿用同樣過濾條件。"""
    where, params = build_filters(args)
    like_clauses = []
    like_params = []
    for t in terms:
        esc = t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_clauses.append("c.text LIKE ? ESCAPE '\\'")
        like_params.append(f"%{esc}%")
    sql = (
        "SELECT c.id, c.ep, c.date, c.kind, c.symbol, c.industry, c.stance, c.t_start, c.text, "
        "0 AS score "
        "FROM chunks c WHERE " + " AND ".join(like_clauses) + where +
        " ORDER BY c.date DESC LIMIT ?"
    )
    return conn.execute(sql, like_params + params + [limit]).fetchall()


def keyword_search(conn, args, limit):
    # FTS5 trigram tokenizer 需要 >=3 字元才能組出 trigram；
    # 兩字中文詞（停損/部位/台股…）MATCH 一律落空，退回 LIKE 全表掃描。
    terms = args.q.split() or [args.q]
    if any(len(t) < 3 for t in terms):
        return _like_search(conn, args, terms, limit)

    where, params = build_filters(args)
    q = args.q.replace('"', '""')
    sql = (
        "SELECT c.id, c.ep, c.date, c.kind, c.symbol, c.industry, c.stance, c.t_start, c.text, "
        "bm25(chunks_fts) AS score "
        "FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.id "
        "WHERE chunks_fts.text MATCH ?" + where +
        " ORDER BY score LIMIT ?"
    )
    params = [f'"{q}"'] + params + [limit]
    return conn.execute(sql, params).fetchall()


def get_meta(conn):
    rows = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    return rows


def embed_query(conn, meta, text):
    model = meta.get("model")
    needs_input_type = meta.get("input_type_mode") == "passage_query"
    vecs = embed_batch(model, needs_input_type, [text], input_type="query")
    return vecs[0]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def semantic_search(conn, args, limit, meta):
    qvec = embed_query(conn, meta, args.q)
    dim = int(meta["dim"])
    where, params = build_filters(args)
    sql = (
        "SELECT c.id, c.ep, c.date, c.kind, c.symbol, c.industry, c.stance, c.t_start, c.text, e.vec "
        "FROM chunks c JOIN embeddings e ON c.id = e.id WHERE 1=1" + where
    )
    rows = conn.execute(sql, params).fetchall()
    scored = []
    for r in rows:
        vec = struct.unpack(f"<{dim}e", r[-1])
        sim = cosine(qvec, vec)
        scored.append((sim, r[:-1]))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def hybrid_search(conn, args, limit, meta):
    kw = keyword_search(conn, args, limit * 3)
    kw_ids = [r[0] for r in kw]
    by_id = {r[0]: r[:9] for r in kw}

    if meta:
        sem = semantic_search(conn, args, limit * 3, meta)
        sem_ids = [r[0] for r in sem]
        for r in sem:
            by_id.setdefault(r[0], r)
    else:
        sem_ids = []

    rrf = {}
    for rank, cid in enumerate(kw_ids):
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (60 + rank)
    for rank, cid in enumerate(sem_ids):
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (60 + rank)

    ranked = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [by_id[cid] for cid, _ in ranked if cid in by_id]


def print_results(rows):
    if not rows:
        print("（無結果）")
        return
    for r in rows:
        _id, ep, date, kind, symbol, industry, stance, t_start, text = r[:9]
        tag = symbol or industry or "-"
        head = f"[{ep or '-'} {date or '-'} {kind or '-'} {tag} {stance or '-'} {t_start or '-'}]"
        snippet = (text or "").replace("\n", " ")[:200]
        print(f"{head} {snippet}")


def main():
    args = parse_args()
    if not DB_PATH.exists():
        print(f"找不到索引 db：{DB_PATH}，請先跑 python scripts/rag_build_index.py")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    if not args.q:
        rows = fetch_filtered(conn, args, order="c.date DESC", limit=args.k)
        print_results(rows)
        conn.close()
        return

    meta = get_meta(conn)
    has_vectors = bool(meta.get("model")) and conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] > 0

    mode = args.mode
    if mode in ("semantic", "hybrid") and not has_vectors:
        print(f"（提示：索引尚無向量，{mode} 模式降級為 keyword）")
        mode = "keyword"

    if mode == "keyword":
        rows = keyword_search(conn, args, args.k)
    elif mode == "semantic":
        rows = semantic_search(conn, args, args.k, meta)
    else:
        rows = hybrid_search(conn, args, args.k, meta)

    print_results(rows)
    conn.close()


if __name__ == "__main__":
    main()
