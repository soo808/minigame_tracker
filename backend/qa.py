"""AI Q&A: three-layer retrieval — Text2SQL + FAISS KB + external hot events.

All LLM calls use the local Qwen model via llm_env.chat_completions_create().
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from backend import db
from backend.llm_env import (
    chat_completions_create,
    extract_completion_text,
    has_llm_for_chat,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema context injected into every Text2SQL prompt
# ---------------------------------------------------------------------------
_SCHEMA_CONTEXT = """
SQLite database schema:
  games(appid TEXT PK, platform TEXT, name TEXT, description TEXT,
        genre_major TEXT, genre_minor TEXT, icon_url TEXT, tags TEXT,
        developer TEXT, first_seen TEXT, updated_at TEXT)
  rankings(id INT PK, date TEXT, platform TEXT, chart TEXT, rank INT, appid TEXT)
    chart values: popularity | bestseller | most_played | fresh_game | popular | new_game
  daily_status(date TEXT, platform TEXT, chart TEXT, appid TEXT,
               is_new INT, is_dropped INT, rank_delta INT)
    rank_delta = today_rank - yesterday_rank  (negative = moved up)
  snapshots(id INT PK, date TEXT, platform TEXT, chart TEXT,
            fetched_at TEXT, status TEXT, game_count INT, note TEXT)
  adx_creatives(creative_id TEXT PK, title TEXT, body_text TEXT,
        product_id TEXT, product_name TEXT, product_icon TEXT,
        platform TEXT, material_type TEXT, grade TEXT,
        composite_score REAL, days_on_chart INT, rising_speed REAL,
        material_num INT, creative_num INT, exposure_num INT,
        exposure_per_creative INT, freshness REAL)

platform values: wx | dy | yyb
Output: valid SQLite SELECT statement only. No INSERT/UPDATE/DELETE/DROP/CREATE.
""".strip()

_BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE)\b",
    re.IGNORECASE,
)


def _extract_sql(text: str) -> str:
    """Extract the first SQL SELECT statement from model output."""
    text = re.sub(r"```(?:sql)?\s*", "", text, flags=re.IGNORECASE).strip()
    text = text.rstrip("`").strip()
    # Find the SELECT statement even if surrounded by other text
    m = re.search(r"(SELECT\b.+)", text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).split(";")[0].strip()
    return text.split(";")[0].strip()


def _get_llm_content(resp: Any) -> str:
    """Extract assistant text: content first, else reasoning (Qwen3 thinking)."""
    return extract_completion_text(resp)


def _qa_answer_max_tokens() -> int:
    raw = os.environ.get("QA_ANSWER_MAX_TOKENS", "1024").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 1024
    return max(256, min(n, 2048))


def _qa_text2sql_max_tokens() -> int:
    raw = os.environ.get("QA_TEXT2SQL_MAX_TOKENS", "1024").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 1024
    return max(128, min(n, 2048))


# ---------------------------------------------------------------------------
# Layer 1: Text2SQL
# ---------------------------------------------------------------------------

def run_text2sql(
    question: str,
    platform: str = "wx",
    date: str | None = None,
) -> dict[str, Any]:
    """Generate and execute a SQL query from natural language using local Qwen."""
    if not has_llm_for_chat():
        return {"sql": None, "rows": [], "error": "no LLM configured"}

    if not date:
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(date) AS d FROM rankings WHERE platform = ?", (platform,)
            ).fetchone()
            date = row["d"] if row and row["d"] else "unknown"

    prompt = (
        f"{_SCHEMA_CONTEXT}\n\n"
        f"Current date: {date}  Current platform filter: {platform}\n\n"
        f"Question: {question}\n\n"
        "Write a single SQLite SELECT query to answer this question. "
        "Use the platform and date filters where appropriate. "
        "If the question asks about rankings, join with games table to get names. "
        "Output the SQL statement only, no explanation."
    )

    try:
        resp = chat_completions_create(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_qa_text2sql_max_tokens(),
            temperature=0.1,
        )
        raw_sql = _get_llm_content(resp)
        sql = _extract_sql(raw_sql)
    except Exception as exc:
        logger.error("Text2SQL model call failed: %s", exc)
        return {"sql": None, "rows": [], "error": str(exc)}

    if _BLOCKED_KEYWORDS.search(sql):
        logger.warning("Text2SQL blocked destructive SQL: %s", sql)
        return {"sql": sql, "rows": [], "error": "blocked: destructive SQL not allowed"}

    if not sql.upper().startswith("SELECT"):
        return {"sql": sql, "rows": [], "error": "model did not return a SELECT query"}

    try:
        with db.get_conn() as conn:
            rows = conn.execute(sql).fetchall()
            result_rows = [dict(r) for r in rows[:50]]
            return {"sql": sql, "rows": result_rows, "error": None}
    except Exception as exc:
        logger.error("Text2SQL execution error sql=%s: %s", sql, exc)
        return {"sql": sql, "rows": [], "error": str(exc)}


# ---------------------------------------------------------------------------
# Layer 2: Local KB (FAISS + sentence-transformers)
# ---------------------------------------------------------------------------

_DEFAULT_KB_DIR = str(Path(__file__).resolve().parent.parent / "data" / "kb")
_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 50

_embed_model_instance: Any = None


def _get_embed_model():
    """Lazy singleton SentenceTransformer (shared by index_kb and search_kb)."""
    global _embed_model_instance
    if _embed_model_instance is None:
        from sentence_transformers import SentenceTransformer

        _embed_model_instance = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2"
        )
    return _embed_model_instance


def _split_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append(text[start:end])
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


def index_kb(kb_dir: str = _DEFAULT_KB_DIR) -> dict:
    """Vectorize all .txt/.pdf files in kb_dir and write FAISS index + chunks.json."""
    try:
        import faiss
        import numpy as np
    except ImportError:
        return {"indexed": 0, "files": [], "error": "faiss-cpu / numpy not installed"}

    kb_path = Path(kb_dir)
    kb_path.mkdir(parents=True, exist_ok=True)

    model = _get_embed_model()
    all_chunks: list[dict] = []
    files_processed = []

    for f in sorted(kb_path.iterdir()):
        if f.suffix.lower() == ".txt":
            text = f.read_text(encoding="utf-8", errors="ignore")
        elif f.suffix.lower() == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(f))
                text = "\n".join(p.extract_text() or "" for p in reader.pages)
            except Exception as exc:
                logger.warning("PDF read failed %s: %s", f.name, exc)
                continue
        else:
            continue

        for chunk in _split_text(text):
            if chunk.strip():
                all_chunks.append({"text": chunk.strip(), "source": f.name})
        files_processed.append(f.name)

    if not all_chunks:
        return {"indexed": 0, "files": []}

    texts = [c["text"] for c in all_chunks]
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=False)
    embeddings_np = np.array(embeddings, dtype="float32")

    dim = embeddings_np.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings_np)

    faiss.write_index(index, str(kb_path / "index.faiss"))
    (kb_path / "chunks.json").write_text(
        json.dumps(all_chunks, ensure_ascii=False), encoding="utf-8"
    )
    return {"indexed": len(all_chunks), "files": files_processed}


def search_kb(
    query: str,
    kb_dir: str = _DEFAULT_KB_DIR,
    top_k: int = 3,
) -> list[str]:
    """Search FAISS index for chunks relevant to query."""
    try:
        import faiss
        import numpy as np
    except ImportError:
        logger.debug("faiss/numpy not installed – skipping KB search")
        return []

    kb_path = Path(kb_dir)
    index_path = kb_path / "index.faiss"
    chunks_path = kb_path / "chunks.json"

    if not index_path.exists() or not chunks_path.exists():
        return []

    try:
        model = _get_embed_model()
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        index = faiss.read_index(str(index_path))

        q_vec = np.array(model.encode([query]), dtype="float32")
        _distances, indices = index.search(q_vec, min(top_k, len(chunks)))
        return [chunks[i]["text"] for i in indices[0] if 0 <= i < len(chunks)]
    except Exception as exc:
        logger.error("search_kb error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Layer 3: External hot events
# ---------------------------------------------------------------------------

_HOT_KEYWORDS = re.compile(r"热点|热榜|最新动态|行业|新闻|今日资讯", re.IGNORECASE)
# If user also asks for leaderboard/db facts, still run Text2SQL.
_SQL_INTENT_PATTERN = re.compile(
    r"榜|排名|排行|上升|下降|新上|品类|分布|在榜|TOP|top|多少|几款游戏|sqlite|数据库",
    re.IGNORECASE,
)
_UAPIS_URL = "https://uapis.cn/api/hotlist?type=wechat"
_GAMERES_RSS = "https://www.gameres.com/feed"


def _is_hot_topic_question(question: str) -> bool:
    return bool(_HOT_KEYWORDS.search(question))


def _needs_hot_events(question: str) -> bool:
    return _is_hot_topic_question(question)


def _should_skip_text2sql(question: str) -> bool:
    """Hot-only questions skip the Text2SQL LLM round (saves time + VRAM)."""
    if not _is_hot_topic_question(question):
        return False
    if _SQL_INTENT_PATTERN.search(question):
        return False
    return True


def fetch_hot_events() -> list[str]:
    """Fetch hot events from uapis.cn and/or gameres RSS."""
    import httpx

    items: list[str] = []

    try:
        resp = httpx.get(_UAPIS_URL, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            for entry in (data.get("data") or [])[:10]:
                title = entry.get("title") or entry.get("name") or ""
                if title:
                    items.append(f"热点：{title}")
    except Exception as exc:
        logger.warning("uapis.cn fetch failed: %s", exc)

    try:
        import feedparser
        feed = feedparser.parse(_GAMERES_RSS)
        for entry in feed.entries[:5]:
            title = getattr(entry, "title", "")
            if title:
                items.append(f"资讯：{title}")
    except Exception as exc:
        logger.warning("gameres RSS fetch failed: %s", exc)

    return items


# ---------------------------------------------------------------------------
# Answer assembly (using local Qwen)
# ---------------------------------------------------------------------------

def answer_question(
    question: str,
    sql_result: dict,
    kb_chunks: list[str],
    hot_events: list[str],
) -> dict:
    """Assemble context from three layers and call Qwen to generate final answer."""
    if not has_llm_for_chat():
        return {"answer": "未配置 LLM，请检查 .env 中的 OPENAI_LOCAL_BASE_URL 和 OPENAI_LOCAL_MODEL", "sql": None, "sources": []}

    parts: list[str] = []
    sources: list[str] = []

    if sql_result.get("rows"):
        rows_text = json.dumps(sql_result["rows"][:20], ensure_ascii=False, indent=2)
        parts.append(f"【数据库查询结果】\nSQL: {sql_result['sql']}\n{rows_text}")
        sources.append("数据库")
    elif sql_result.get("error"):
        parts.append(f"【数据库查询失败】{sql_result['error']}")

    if kb_chunks:
        kb_text = "\n---\n".join(kb_chunks[:3])
        parts.append(f"【知识库片段】\n{kb_text}")
        sources.append("本地知识库")

    if hot_events:
        parts.append("【外部热点】\n" + "\n".join(hot_events[:10]))
        sources.append("外部热点")

    context = "\n\n".join(parts) if parts else "（无可用数据）"

    prompt = (
        f"你是微信/抖音/应用宝小游戏市场分析助手。\n"
        f"用户问题：{question}\n\n"
        f"参考资料：\n{context}\n\n"
        "请根据以上资料，用简洁中文回答用户问题。"
        "回答中要引用具体的数据和游戏名。"
        "如果资料不足，直接说明。不要编造数据。"
    )

    try:
        resp = chat_completions_create(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_qa_answer_max_tokens(),
            temperature=0.3,
        )
        answer = _get_llm_content(resp)
    except Exception as exc:
        logger.error("answer_question model call failed: %s", exc)
        answer = f"生成回答时出错：{exc}"

    return {"answer": answer, "sql": sql_result.get("sql"), "sources": sources}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def qa_pipeline(
    question: str,
    platform: str = "wx",
    date: str | None = None,
    kb_dir: str = _DEFAULT_KB_DIR,
) -> dict:
    """Full three-layer QA pipeline."""
    if _should_skip_text2sql(question):
        sql_result: dict[str, Any] = {
            "sql": None,
            "rows": [],
            "error": None,
        }
    else:
        sql_result = run_text2sql(question, platform=platform, date=date)

    kb_chunks = search_kb(question, kb_dir=kb_dir)

    hot_events: list[str] = []
    if _needs_hot_events(question):
        hot_events = fetch_hot_events()

    return answer_question(question, sql_result, kb_chunks, hot_events)
