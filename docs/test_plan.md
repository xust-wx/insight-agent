# 测试计划与质量门禁（Test Plan）

> 版本：v0.2。测试按是否依赖外部资源（Docker / LLM API）严格分层，保障 GitHub Actions CI 可免密快速运行。

## 1. 测试分层架构

| 层级 | 目录 / 脚本 | 外部依赖 | 执行时机 | 目标覆盖内容 |
| :-- | :-- | :-- | :-- | :-- |
| **L1 纯单元测试** | `tests/unit/` | 无（Mock LLM/DB） | 每次提交 + GitHub Actions CI | `sql_guard` AST 校验、`insight_sandbox_lib` 数学拆解函数（加法/LMDI/PVM/零值边界）、数字溯源幻觉检测器、配置与口径 YAML 解析、状态机路由与熔断逻辑 |
| **L2 安全专项测试** | `tests/security/` | 无 / 可选本地 Postgres | 每次提交 + S3 门禁 | 执行 `docs/security_cases.md` 全部攻击载荷，断言 100% 阻断 |
| **L3 基础设施集成测试** | `tests/integration/` | 本地 Docker（Postgres + 沙箱），Mock LLM | S1 / S2 / S5 本地门禁 | 只读账号权限拒绝、口径字典 `validate_glossary.py` 全量 SQL 执行、沙箱断网/只读/`matplotlib` 出图/超时强杀、Checkpointer 中断与恢复 |
| **L4 端到端冒烟与回归评测** | `scripts/smoke_test_llm.py` + `scripts/run_eval.py` | 真实 LLM API + Docker | S1 入口（冒烟）、S4（全量 Eval） | 真实模型连通性、Golden Dataset 40~50 题准确率、幻觉率、延迟与 Token 统计 |

## 2. 核心数学库必测边界（`tests/unit/test_analysis_lib.py`）
1. **加法贡献拆解**：各子项变化之和严格等于总变化（`Σ ΔY_i == ΔY`）；总变化为 `0` 时不抛除零异常。
2. **LMDI 两因素分解**：正值输入下 `订单量效应 + 客单价效应 == 总 GMV 变化`（残差 `< 1e-9`）；存在 `0` 值时自动平滑退化为均值差分分解并标记方法名。
3. **PVM 结构效应**：构造经典辛普森悖论算例（A/B 两品类单价均上涨，但低价品类销量占比大增导致整体均价下跌），验证函数能准确拆出正价格效应与负结构（Mix）效应。

## 3. CI 流水线策略（S5 落地 `.github/workflows/ci.yml`）
- 触发：`push` 与 `pull_request` 到 `main`。
- 步骤：`ruff check` → `ruff format --check` → 口径字典 YAML 结构校验 → `pytest tests/unit tests/security -m "not integration"`（全程无需 `GEMINI_API_KEY` 与Kaggle 数据，2 分钟内完成）。
