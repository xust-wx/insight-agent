"""Domain-aware Chinese + English tokenizer using jieba for PostgreSQL tsvector FTS (P0-3 fix)."""

from __future__ import annotations

import re
from functools import lru_cache

import jieba
import yaml

from insight_agent.config import get_settings

TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]+")
STOPWORDS: frozenset[str] = frozenset(
    {
        "的",
        "了",
        "和",
        "与",
        "及",
        "或",
        "在",
        "中",
        "是",
        "有",
        "按",
        "看",
        "各",
        "什么",
        "多少",
        "哪些",
        "如何",
        "请问",
        "统计",
        "查询",
        "分析",
        "计算",
    }
)


@lru_cache(maxsize=1)
def _init_jieba() -> jieba.Tokenizer:
    tok = jieba.Tokenizer()
    tok.initialize()
    settings = get_settings()
    if settings.glossary_path.exists():
        with settings.glossary_path.open("r", encoding="utf-8") as f:
            glossary = yaml.safe_load(f) or {}
        for m in glossary.get("metrics", []):
            if m.get("name"):
                tok.add_word(str(m["name"]), freq=20000)
            for alias in m.get("aliases", []):
                tok.add_word(str(alias), freq=20000)
        for dim in (glossary.get("dimensions") or {}).values():
            for alias in dim.get("aliases", []):
                tok.add_word(str(alias), freq=20000)
        for rule in glossary.get("ambiguity_rules", []):
            for term in rule.get("term_triggers", []):
                tok.add_word(str(term), freq=20000)
    # High-frequency analytical domain terms
    for word in (
        "成交额",
        "销售额",
        "客单价",
        "复购率",
        "逾期率",
        "延迟交付率",
        "差评率",
        "平均评分",
        "订单量",
        "订单数",
        "买家数",
        "履约时效",
        "贡献拆解",
        "同环比",
        "辛普森悖论",
    ):
        tok.add_word(word, freq=25000)
    return tok


def extract_tokens(text: str) -> list[str]:
    """Segment Chinese + English text into normalized search tokens."""
    if not text:
        return []
    tok = _init_jieba()
    raw_pieces = tok.cut_for_search(text.lower())
    result: list[str] = []
    for piece in raw_pieces:
        for match in TOKEN_PATTERN.findall(piece):
            if match and match not in STOPWORDS:
                result.append(match)
    return result


def tokenize_for_fts(text: str) -> str:
    """Return space-delimited tokens suitable for PostgreSQL `to_tsvector('simple', ...)`."""
    return " ".join(extract_tokens(text))


def build_or_tsquery(query_text: str) -> str:
    """Build a safe OR-joined PostgreSQL tsquery string (e.g. `'成交额' | 'gmv'`)."""
    seen: dict[str, None] = {}
    for t in extract_tokens(query_text):
        # Escape any single quotes defensively (TOKEN_PATTERN already strips them)
        safe = t.replace("'", "")
        if safe:
            seen[safe] = None
    if not seen:
        return ""
    return " | ".join(f"'{tok}'" for tok in seen)
