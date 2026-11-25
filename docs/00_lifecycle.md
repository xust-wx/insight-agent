# 00 · 项目开发生命周期与阶段门禁（v0.2）

> 本文件是项目的**总控文档**：每个阶段完成后，更新下方“进度看板”，并把产出文档归档到对应目录。
> 原则：**文档先行 → 评审闭环 → 骨架打通 → 能力深化 → 评测驱动 → 加固交付 → 复盘沉淀**。

## 进度看板与工期预算

| 阶段 | 名称 | 预估工期 | 负责人 | 状态 | 关键产出文档 | 完成日期 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| S0 | 需求对齐与技术设计 | 1.5 人天 | 架构/研发 | ✅ v0.2 修订完成（API 连通性待 S1 入口验证） | `01_PRD.md` `02_TDD.md` `03_metrics_glossary.yaml` `test_plan.md` `security_cases.md` `adr/ADR-001~006` | 2026-11-24 |
| S1 | 数据底座、EDA 与语义层 | 2.0 人天 | 数据/研发 | ⏳ 未开始 | `04_data_setup.md` `eda_findings.md` `stage_reports/S1.md` | |
| S2 | MVP 骨架与主链路联调 | 2.5 人天 | 研发 | ⏳ 未开始 | `05_api_contract.md` `stage_reports/S2.md` | |
| S3 | 核心 Agent 能力深化 | 3.5 人天 | 研发 | ⏳ 未开始 | `stage_reports/S3.md` | |
| S4 | 评测体系与数据驱动优化 | 3.0 人天 | 研发/评测 | ⏳ 未开始 | `06_eval_report.md` `stage_reports/S4.md` | |
| S5 | 交互界面与生产化加固 | 2.0 人天 | 全栈/研发 | ⏳ 未开始 | `07_runbook.md` `stage_reports/S5.md` | |
| S6 | 复盘与成果沉淀 | 1.0 人天 | 研发 | ⏳ 未开始 | `08_retrospective.md` | |

## 评审记录

| 阶段 | 评审版本 | 评审结论 | 评审报告 | 修订闭环版本 |
| :-- | :-- | :-- | :-- | :-- |
| S0 | v0.1 (`s0-done`) | 有条件通过（4 项 P0、7 项 P1、11 项 P2） | `stage_reports/S0_review.md` | v0.2（当前版本，待推送并打 `s0-v0.2` 标签；S1 入口完成 API 实测后归档） |

## 阶段定义与门禁（Definition of Done）

### S0 需求对齐与技术设计
- 产出：PRD、TDD、可执行指标口径字典、测试计划、安全用例库、关键架构决策记录（ADR-001~006）、开源许可声明（`LICENSE`）。
- 门禁：
  - 范围 / 非目标 / 分档 KPI 与测量方法 / 安全红线 / 架构 / 接口契约全部成文。
  - 完成独立技术评审（`S0_review.md`），所有 P0/P1 设计缺口在 v0.2 中闭环。
  - `03_metrics_glossary.yaml` 通过 YAML 语法与结构完整性校验。

### S1 数据底座、EDA 与语义层
- 内容：
  1. **入口冒烟检查**：运行 `scripts/smoke_test_llm.py` 验证百炼 `DASHSCOPE_API_KEY`、`qwen4-max` 与 `qwen3.7-text-embedding-flash`（`1024` 维 float 向量）直连连通性。
  2. Docker 拉起 PostgreSQL 16 + `pgvector`（仅绑定 `127.0.0.1`）；导入 Olist 公开数据集（9 表），校验 SHA256 与行数，创建标准化分析视图（修复拼写、去重评价、品类兜底）。
  3. 创建严格只读账号（`default_transaction_read_only = on` + 超时限制）。
  4. 运行 `scripts/validate_glossary.py`，逐条执行口径字典中的 `sql_template`，确保 100% 可执行且无语法/关联错误。
  5. **数据探索（EDA）**：产出 `docs/eda_findings.md`，核实真实异动月份、州、品类及数据稀疏区间，回填 PRD 示例与评测题素材。
  6. 构建口径 / Few-shot 混合检索索引，并生成可选的“30 张合成干扰表 schema”供 S4 召回压测使用。
- 门禁：
  - LLM 连通性脚本返回 200 OK，实际型号写入 `ADR-001`。
  - `docker compose up -d` 一键启动；9 张表行数与官方一致；`validate_glossary.py` 全绿。
  - 只读账号执行 DML/DDL、可写 CTE、系统函数均被拒绝。
  - `eda_findings.md` 完成真实异动事实归档。

### S2 MVP 骨架（Walking Skeleton）
- 内容：`pyproject.toml` + `ruff` + `pytest` 工程初始化；MCP Server v0.1（上下文检索 + AST 安全只读 SQL）；加固版常驻 Docker 沙箱（含预置 `insight_sandbox_lib` 分析库）；LangGraph 最小闭环 + Postgres Checkpointer；FastAPI + SSE + 恢复接口；本地 JSONL + OpenTelemetry Trace。
- 门禁：1 条真实问题端到端跑通（查数 → 沙箱计算出图 → 流式报告），Trace 完整记录延迟与 Token；核心单测通过。

### S3 核心能力深化
- 内容：定量贡献度拆解（维度加总拆解、LMDI 两因素分解、PVM 价格-销量-结构效应、时序异常检测）；反思自修复 + 步数/重试熔断；口径歧义与稀疏区间 HITL 中断恢复；大结果集落盘摘要压缩与用户口径记忆；多层安全护栏。
- 门禁：复杂贡献拆解问题输出带完整数字溯源与因果免责声明的报告；`security_cases.md` 中的攻击用例 100% 拦截；死循环用例在上限内优雅降级。

### S4 评测驱动优化
- 内容：人工编写并验证的 Golden Dataset（≥ 40 题，覆盖 4 类场景）；自动化评测流水线（断点续跑 + 缓存 + 数值溯源幻觉检测）；`v0-baseline → v1 → v2` 对比实验（含 9 表常规模式与 +30 干扰表模式）；Bad Case 根因分类。
- 门禁：一条命令复现评测报告；核心指标满足 PRD v0.2 目标值与相对提升要求。

### S5 加固与交付
- 内容：轻量前端演示页（展示步骤、SQL、图表、HITL 确认交互）；LLM 指数退避重试与多提供商 Fallback；结构化脱敏日志；GitHub Actions CI（跑 lint 与免密单测）；README 与 Runbook。
- 门禁：测试全绿；按 README 30 分钟内可在新环境拉起。

### S6 复盘沉淀
- 内容：最终架构图、真实演示截图/录屏、踩坑复盘与面试高频追问应答手册。

## 文档目录约定

```text
docs/
├── 00_lifecycle.md          # 本文件：生命周期、工期、评审记录与阶段门禁
├── 01_PRD.md                # 产品需求（v0.2）
├── 02_TDD.md                # 技术设计（v0.2）
├── 03_metrics_glossary.yaml # 可执行指标口径字典与维度兼容矩阵（v0.2）
├── 04_data_setup.md         # S1 数据底座与清洗视图说明
├── eda_findings.md          # S1 Olist 真实数据探索与异动事实记录
├── 05_api_contract.md       # S2 接口契约（REST / SSE / MCP 定稿）
├── 06_eval_report.md        # S4 评测对比与 Bad Case 分析报告
├── 07_runbook.md            # S5 运维、代理配置与排障手册
├── 08_retrospective.md      # S6 项目复盘
├── test_plan.md             # 测试分层策略与质量门禁
├── security_cases.md        # SQL 注入 / Prompt 注入 / 沙箱逃逸安全测试清单
├── adr/                     # 架构决策记录（ADR-001 ~ ADR-006）
└── stage_reports/           # 每阶段验收与评审报告
```

## 每阶段固定动作
1. 开工前：确认上一阶段遗留问题与入口条件，在 `stage_reports/Sx.md` 明确本阶段目标。
2. 开发中：架构与选型变更必须写入 `adr/ADR-xxx.md`，严禁文档与代码脱节。
3. 收尾时：执行门禁脚本与测试 → 填写验收结果与遗留问题 → 更新进度看板 → `CHANGELOG.md` 记录 → Git 打阶段标签并推送。
