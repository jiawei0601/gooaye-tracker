#!/usr/bin/env python3
"""股癌 AI 分身聊天後端（FastAPI）。

啟動：uvicorn server.twin_server:app --host 127.0.0.1 --port 8788
（repo 根目錄執行；Caddy 用 handle_path 剝掉 /gooaye 前綴後 reverse_proxy 到這裡，
 所以本檔路由是 /health /chat，不含 /gooaye 前綴）。

流程（POST /chat）：
  1. 驗證 Authorization: Bearer <token>（token 可能含非 ASCII，前端會 encodeURIComponent，
     這裡 urllib.parse.unquote 還原後用 constant-time 比較）。
  2. 限流：每 IP 每分鐘 10 則（記憶體滑動窗，重啟即清零）。
  3. hybrid 檢索使用者訊息（重用 scripts/rag_query.py 的 FTS5 + NIM 語意腿邏輯，
     語意腿失敗自動降級 OpenRouter 同款 bge-m3，再失敗降級純關鍵字）。
  4. 組 prompt：persona_system.md ＋ 檢索到的節目內容 ＋ history ＋ 使用者訊息。
  5. 生成雙通道：主力 NIM deepseek-v4-pro（timeout 40 秒），逾時或 429/5xx 退 DeepSeek 官方。
  6. 回 {"reply": ..., "sources": [...], "channel": "nim|deepseek"}（channel 為除錯用選用欄位）。
"""
import hmac
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import common  # noqa: E402  (scripts/common.py)
import rag_query as rq  # noqa: E402  (scripts/rag_query.py)
from rag_build_index import embed_batch as nim_embed_batch  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("gooaye-twin")

DB_PATH = ROOT / "data" / "rag" / "gooaye.db"
PERSONA_PATH = Path(__file__).resolve().parent / "persona_system.md"

RATE_LIMIT_PER_MIN = 10
RATE_WINDOW_SEC = 60.0
HISTORY_CAP = 10
RETRIEVE_K = 8

OPENROUTER_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"
OPENROUTER_EMBED_MODEL = "baai/bge-m3"
NIM_CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_CHAT_MODEL = "deepseek-ai/deepseek-v4-pro"
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_CHAT_MODEL = "deepseek-chat"

FRONTEND_ORIGIN = "https://jiawei0601.github.io"

# ---------------------------------------------------------------------------
# 啟動時載入設定
# ---------------------------------------------------------------------------

common.load_env()
PERSONA_SYSTEM = PERSONA_PATH.read_text(encoding="utf-8")

EXTRAS_KINDS = {"qa", "chat", "joke", "wisdom", "macro"}


# ---------------------------------------------------------------------------
# Embedding 語意腿：NIM 主力，失敗降級 OpenRouter 同款 bge-m3
# ---------------------------------------------------------------------------

def _openrouter_embed(texts):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY 未設定，無法降級 OpenRouter embedding")
    payload = {"model": OPENROUTER_EMBED_MODEL, "input": texts}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_EMBED_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    items = sorted(body["data"], key=lambda d: d.get("index", 0))
    return [d["embedding"] for d in items]


def _combined_embed_batch(model, needs_input_type, texts, input_type="passage"):
    try:
        return nim_embed_batch(model, needs_input_type, texts, input_type=input_type)
    except Exception as e:
        logger.warning("NIM embedding 失敗（%s），嘗試降級 OpenRouter bge-m3", e)
        if "bge-m3" not in model:
            raise
        return _openrouter_embed(texts)


# rag_query.embed_query() 呼叫的是模組層級名稱 rag_query.embed_batch；
# 換成含降級邏輯的版本，hybrid_search/semantic_search 不用改。
rq.embed_batch = _combined_embed_batch


def _open_db():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def retrieve(query_text: str, k: int = RETRIEVE_K):
    """hybrid 檢索：keyword+semantic RRF；語意腿全滅或索引異常時退純關鍵字。"""
    if not DB_PATH.exists():
        return []
    conn = _open_db()
    try:
        args = SimpleNamespace(
            q=query_text, since=None, until=None, ep=None, symbol=None,
            industry=None, stance=None, kind=None, category=None,
        )
        meta = rq.get_meta(conn)
        has_vectors = (
            bool(meta.get("model"))
            and conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] > 0
        )
        if not has_vectors:
            return rq.keyword_search(conn, args, k)
        try:
            return rq.hybrid_search(conn, args, k, meta)
        except Exception as e:
            logger.warning("hybrid_search 失敗（%s），降級純關鍵字檢索", e)
            return rq.keyword_search(conn, args, k)
    finally:
        conn.close()


def format_context(rows) -> str:
    if not rows:
        return "（本次沒有檢索到相關節目內容）"
    lines = []
    for r in rows:
        _id, ep, date, kind, symbol, industry, stance, t_start, category, text = r[:10]
        tag = symbol or industry or category or "-"
        lines.append(f"[{ep or '-'} {date or '-'} {kind or '-'} {tag}] {(text or '').strip()}")
    return "\n\n".join(lines)


def build_sources(rows):
    seen = set()
    sources = []
    for r in rows:
        _id, ep, date, kind, *_ = r[:10]
        key = (ep, kind, date)
        if key in seen or not ep:
            continue
        seen.add(key)
        sources.append({"ep": ep, "kind": kind, "date": date})
    return sources


# ---------------------------------------------------------------------------
# 生成雙通道：主力 NIM deepseek-v4-pro，逾時/429/5xx 退 DeepSeek 官方
# ---------------------------------------------------------------------------

def _post_chat(url, api_key, model, messages, timeout):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1200,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def call_nim_chat(messages):
    api_key = os.environ.get("NVIDIA_NIM_API_KEY")
    if not api_key:
        raise RuntimeError("NVIDIA_NIM_API_KEY 未設定")
    return _post_chat(NIM_CHAT_URL, api_key, NIM_CHAT_MODEL, messages, timeout=40)


def call_deepseek_chat(messages):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未設定")
    return _post_chat(DEEPSEEK_CHAT_URL, api_key, DEEPSEEK_CHAT_MODEL, messages, timeout=60)


def generate_reply(messages):
    """主力 NIM，逾時/429/5xx/任何錯誤都退 DeepSeek 官方。回傳 (text, channel)。"""
    try:
        return call_nim_chat(messages), "nim"
    except Exception as e:
        logger.warning("NIM 主力生成失敗（%s），退 DeepSeek 官方", e)
        try:
            return call_deepseek_chat(messages), "deepseek"
        except Exception as e2:
            raise RuntimeError(f"雙通道皆失敗：NIM={e}；DeepSeek={e2}") from e2


# ---------------------------------------------------------------------------
# 認證：token 可能含非 ASCII，前端 encodeURIComponent 送出，這裡 unquote 還原
# ---------------------------------------------------------------------------

def verify_token(auth_header: Optional[str]) -> bool:
    expected = os.environ.get("GOOAYE_TWIN_TOKEN", "")
    if not expected or not auth_header:
        return False
    if not auth_header.startswith("Bearer "):
        return False
    raw = auth_header[len("Bearer "):].strip()
    try:
        decoded = unquote(raw)
    except Exception:
        decoded = raw
    return hmac.compare_digest(decoded.encode("utf-8"), expected.encode("utf-8"))


# ---------------------------------------------------------------------------
# 限流：記憶體滑動窗，每 IP 每分鐘 10 則
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_rate_buckets = defaultdict(deque)


def check_rate_limit(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        bucket = _rate_buckets[ip]
        while bucket and now - bucket[0] > RATE_WINDOW_SEC:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_PER_MIN:
            return False
        bucket.append(now)
        return True


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

class HistoryItem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[HistoryItem] = Field(default_factory=list)


app = FastAPI(title="gooaye-twin")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "null"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    auth_header = request.headers.get("authorization")
    if not verify_token(auth_header):
        raise HTTPException(status_code=401, detail="invalid token")

    ip = client_ip(request)
    if not check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="rate limited, max 10/min")

    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="empty message")

    history = [
        (h.model_dump() if hasattr(h, "model_dump") else h.dict())
        for h in req.history[-HISTORY_CAP:]
    ]

    rows = retrieve(message, k=RETRIEVE_K)
    context_block = format_context(rows)
    sources = build_sources(rows)

    system_content = (
        f"{PERSONA_SYSTEM}\n\n"
        f"== 檢索到的節目內容（引用時標集數）==\n{context_block}"
    )
    messages = [{"role": "system", "content": system_content}]
    for h in history:
        role = h.get("role") if h.get("role") in ("user", "assistant") else "user"
        messages.append({"role": role, "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    try:
        reply, channel = generate_reply(messages)
    except Exception as e:
        logger.error("生成失敗：%s", e)
        raise HTTPException(status_code=502, detail="upstream LLM failed") from e

    return {"reply": reply, "sources": sources, "channel": channel}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8788)
