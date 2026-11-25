"""L1 unit tests for configuration, glossary YAML, few-shot YAML, and Jieba FTS tokenizer."""

from __future__ import annotations

import yaml

from insight_agent.config import get_settings
from insight_agent.semantic.tokenizer import build_or_tsquery, tokenize_for_fts


def test_settings_defaults() -> None:
    settings = get_settings()
    assert settings.llm_model == "qwen4-max"
    assert settings.embedding_model == "qwen3.7-text-embedding-flash"
    assert settings.embedding_dim == 1024
    assert settings.pg_service_user in settings.pg_service_dsn
    assert settings.pg_readonly_user in settings.pg_readonly_dsn


def test_glossary_and_few_shots_yaml_structure() -> None:
    settings = get_settings()
    with settings.glossary_path.open("r", encoding="utf-8") as f:
        glossary = yaml.safe_load(f)

    assert glossary["dataset"] == "olist"
    assert glossary["default_schema"] == "olist_clean"
    assert len(glossary["tables"]) == 9
    assert len(glossary["metrics"]) == 12
    assert len(glossary["known_pitfalls"]) >= 6

    late_metric = next(m for m in glossary["metrics"] if m["id"] == "late_delivery_rate")
    assert "::DATE > o.order_estimated_delivery_date::DATE" in late_metric["sql_template"]

    with settings.few_shots_path.open("r", encoding="utf-8") as f:
        few_shots = yaml.safe_load(f)
    assert len(few_shots["examples"]) >= 4


def test_chinese_domain_tokenization() -> None:
    tokens_str = tokenize_for_fts("2017年各州有效商品成交额GMV（不含运费）与逾期率、90天复购率")
    tokens = set(tokens_str.split())
    for expected in ("成交额", "gmv", "逾期率", "复购率"):
        assert expected in tokens, f"Missing expected domain token '{expected}' in {tokens}"

    tsq = build_or_tsquery("成交额和客单价变化")
    assert "'成交额'" in tsq
    assert "'客单价'" in tsq
