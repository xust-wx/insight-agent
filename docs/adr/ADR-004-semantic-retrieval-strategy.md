# ADR-004 · 语义层与检索策略：全量核心 Schema 常驻 + 混合检索与干扰表压测

- 状态：已接受（2026-11-24）
- 关联评审项：`S0_review.md` P1-2

## 背景
Olist 清洗后仅有 **9 张核心业务表、约 50 个字段**，精简 DDL + 注释仅占 ~1,800 tokens；若强行对 9 张表做向量 Top-K 召回，不仅没有节省多少 Token，反而引入“漏召回关联表”的人为错误。但真实企业数仓往往有数十至上百张表，如何在不造假的前提下同时兼顾实用性与架构说服力？

## 决策
采用**双模式分层检索设计**：
1. **默认生产模式（9 表场景）**：
   - `olist_clean` 核心表的精简 Schema 摘要**常驻注入上下文**（保证 100% 表覆盖，还能命中 LLM Prompt Cache）。
   - **混合检索（`jieba` 领域词典中文分词 + PostgreSQL `tsvector`/`ts_rank_cd` 全文检索 + `pgvector(1024)` 余弦相似度，RRF `k=60` 倒数秩融合）** 专门用于检索：
     - 指标口径模板与不兼容维度规则（`03_metrics_glossary.yaml`）；
     - 经自动执行验证的 Few-shot SQL 样例（`eval/few_shots/verified_sqls.yaml`）；
     - 用户确认过的口径偏好记忆。
   - **中文分词修复（`S1_review` P0-3 闭环）**：PostgreSQL 内置 `simple` 解析器不切分连续中文；应用层统一由 `insight_agent.semantic.tokenizer` 注入业务口径词典（如 `成交额`、`逾期率`、`复购率`、`客单价`）后执行 `jieba.cut_for_search`，写入 `tsv_tokens` 生成 `tsvector`，查询端走一致分词构造 `tsquery`，零额外数据库插件依赖。
2. **数仓扩展压测模式（`include_distractors=True`，S4 专项评测）**：
   - 在 `olist_distractor` Schema 下生成 **30 张带表注释与样本数据的干扰表**，其中包含 **12 张高混淆度电商近义表**（如 `orders_archive_2015`、`order_items_staging`、`gmv_daily_board_deprecated`、`product_reviews_moderation`）及 18 张周边业务表，避免因表名前缀过于明显导致召回率虚高。
   - 在 40 张表总规模下开启表级混合召回（Top-8 表），在 `06_eval_report.md` 中实测汇报 `Recall@8`、Token 节省比例与端到端准确率变化。

## 后果
- 诚实面对数据规模，避免过度设计导致小库准确率下降。
- 在 S4 中既有高准确率的实用表现，又有可复现的多表召回压测实验数据。
