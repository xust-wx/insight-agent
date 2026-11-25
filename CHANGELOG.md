# Changelog

## [s1-done] - 2026-11-25
### Added
- **工程脚手架与百炼客户端**：新增 `pyproject.toml`、`src/insight_agent/config.py`、`src/insight_agent/llm/client.py` 与 `scripts/smoke_test_llm.py`，实测验证 `qwen4-max`（`reasoning_effort="low"` 返回 `reasoning_tokens=17`）与 `qwen3.7-text-embedding-flash`（1024 维 float）国内直连通过，实测数据写入 `ADR-001`。
- **三级权限分离与多层只读安全执行器（闭环 `S1_review` P0-1 & P1-1）**：新增 `infra/db/03_readonly_role.sql`（隔离 `olist_admin` 超级用户、`agent_service` 应用账号与 `readonly_analyst` 只读账号，回收 `TEMP` 建表与 `pg_sleep`）、`src/insight_agent/security/sql_guard.py`（`sqlglot` 全语法树白名单）与 `src/insight_agent/db/readonly_executor.py`（逐事务强制 `BEGIN TRANSACTION READ ONLY` + `SET LOCAL statement_timeout`）。
- **数据治理与高混淆压测集（闭环 P0-2 & P1-5 & P2）**：`scripts/ingest_olist.py` 锁定 Kaggle v2 与 9 表 64 位 SHA256 硬断言；`02_clean_views.sql` 实现评价按单去重、空值与缺失翻译葡语品类 100% 英文映射；构建含 12 张近义混淆表、表注释与样本数据的 30 张 `olist_distractor` 表；修正 `late_delivery_rate` 为自然日 `::DATE > ::DATE` 比较（`6.79%`）。
- **全矩阵口径验证、非因果 EDA 与 Jieba+pgvector 混合检索（闭环 P0-3 & P1-2~P1-4）**：`scripts/validate_glossary.py` 验证 12 模板 + 51 组指标×维度聚合 + 12 项可加性断言 + `eval/few_shots/verified_sqls.yaml` + 17 项安全攻击拦截；新增 `src/insight_agent/semantic/`（`jieba` 领域词典分词 + `tsvector` + `pgvector(1024)` RRF 融合 + `content_hash` 增量嵌入缓存）；产出 `docs/04_data_setup.md`、`docs/eda_findings.md`、`docs/stage_reports/S1_review.md` 与 `docs/stage_reports/S1.md`。

## [s0-v0.3] - 2026-11-25
### Changed
- **模型栈定型 (`ADR-001`, `02_TDD.md`, `.env.example`, `README.md`)**：主生成模型定为阿里云百炼 `qwen4-max`（支持按节点分级控制 `reasoning_effort`），向量嵌入模型定为 `qwen3.7-text-embedding-flash`（`1024` 维，显式指定 `encoding_format="float"` 规避 SDK `base64` 兼容陷阱）；配置国内直连旁路本地系统代理，从根源消除海外 API 地区封锁风险。

## [s0-v0.2] - 2026-11-24
### Changed
- **PRD v0.2 (`docs/01_PRD.md`)**：将“业务归因”严格界定为“定量贡献度拆解（Contribution Decomposition）”并增加非因果免责声明；明确定义 `v0-baseline`、分档延迟 SLA、Token 预算上限与数字溯源幻觉率自动检测口径；修正 HITL 触发条件为口径歧义与稀疏区间确认。
- **TDD v0.2 (`docs/02_TDD.md`)**：补齐 Gemini 地区限制与 `HTTPS_PROXY` / OpenAI 兼容降级设计；设计 `olist_raw` + `olist_clean` 脏数据治理层；升级四层 SQL 防护（全 AST 拦截可写 CTE、函数黑名单、`LIMIT N+1` 截断检测、`default_transaction_read_only`）；改为常驻预热加固 Docker 沙箱（修复 `--read-only` 与 `matplotlib` 冲突，内置 `insight_sandbox_lib` 算法库，增加 PVM 结构效应）；补齐会话记忆、节点 Pydantic Schema、REST/SSE 恢复端点、轻量化 JSONL+OTel 可观测方案与 API 配额预算。
- **口径字典 v0.2 (`docs/03_metrics_glossary.yaml`)**：修复 `reviews` 重复主键、`products` 拼写与空值品类、时区与复购窗口定义；新增指标 × 维度兼容矩阵与 12 条可直接执行的 PostgreSQL `sql_template`。
- **生命周期总控 (`docs/00_lifecycle.md`)**：补充工期预算、评审闭环记录，将 LLM 连通性测试、EDA 与口径模板自动校验纳入 S1 门禁。
- **ADR-001 & ADR-002**：写入具体默认模型型号（`gemini-3.8-flash` / `gemini-3.5-flash-lite` / `gemini-embedding-2`）、地区限制对策与开源许可隔离规则。

### Added
- `docs/stage_reports/S0_review.md`：S0 阶段独立技术评审报告（P0/P1/P2 问题清单）。
- `docs/adr/ADR-004~006`：语义检索双模式（常驻核心表 + 30 干扰表压测）、预热加固沙箱与 Postgres Checkpointer、轻量化可观测性决策记录。
- `docs/test_plan.md` & `docs/security_cases.md`：L1~L4 测试计划与 17 项安全红队测试用例。
- `LICENSE`：MIT 源码许可与 Olist CC BY-NC-SA 4.0 派生署名声明。

## [s0] - 2026-11-24
### Added
- 项目生命周期与阶段门禁初稿（docs/00_lifecycle.md）
- PRD、TDD、指标口径字典、ADR-001~003、S0 阶段报告初稿
