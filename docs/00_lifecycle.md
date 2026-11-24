# 00 · 项目开发生命周期与阶段门禁

> 本文件是项目的**总控文档**：每个阶段完成后，更新下方“进度看板”，并把产出文档归档到对应目录。
> 原则：**文档先行 → 骨架打通 → 能力深化 → 评测驱动 → 加固交付 → 复盘沉淀**。

## 进度看板

| 阶段 | 名称 | 状态 | 关键产出文档 | 完成日期 |
| :-- | :-- | :-- | :-- | :-- |
| S0 | 需求对齐与技术设计 | ✅ 已完成（待评审） | `01_PRD.md` `02_TDD.md` `03_metrics_glossary.yaml` `adr/` | 2026-11-24 |
| S1 | 数据底座与语义层 | ⏳ 未开始 | `04_data_setup.md` `stage_reports/S1.md` | |
| S2 | MVP 骨架与主链路联调 | ⏳ 未开始 | `05_api_contract.md` `stage_reports/S2.md` | |
| S3 | 核心 Agent 能力深化 | ⏳ 未开始 | `stage_reports/S3.md` | |
| S4 | 评测体系与数据驱动优化 | ⏳ 未开始 | `06_eval_report.md` `stage_reports/S4.md` | |
| S5 | 交互界面与生产化加固 | ⏳ 未开始 | `07_runbook.md` `stage_reports/S5.md` | |
| S6 | 复盘与成果沉淀 | ⏳ 未开始 | `08_retrospective.md` | |

## 阶段定义与门禁（Definition of Done）

### S0 需求对齐与技术设计
- 产出：PRD、TDD、指标口径字典、关键技术决策记录（ADR）。
- 门禁：范围 / 非目标 / KPI / 安全红线 / 架构 / 接口契约全部成文并评审通过。

### S1 数据底座与语义层
- 内容：Docker 拉起 PostgreSQL + pgvector；导入 Olist 公开数据集（9 表）；创建只读账号；建立表元数据、指标口径、Few-shot SQL 的向量索引。
- 门禁：
  - `docker compose up` 一键启动；行数校验与官方数据一致。
  - 只读账号执行 `INSERT/UPDATE/DROP` 全部被拒绝。
  - 输入“复购率”“履约时效”等业务词，Top-5 召回命中正确表与口径（人工抽检 ≥ 90%）。

### S2 MVP 骨架（Walking Skeleton）
- 内容：工程目录规范；MCP Server v0.1（Schema 召回 + 只读 SQL）；Docker 沙箱 v0.1；LangGraph 最小闭环；FastAPI + SSE；Trace。
- 门禁：1 条真实问题端到端跑通（查数 → 沙箱计算出图 → 流式报告），Trace 可见完整调用链；冒烟测试通过。

### S3 核心能力深化
- 内容：定量归因工具（维度贡献度 / 因素分解 / 异常检测）；反思自修复 + 熔断；Checkpoint + HITL；上下文压缩与口径记忆；安全护栏。
- 门禁：归因类问题输出带数字溯源的报告；注入攻击用例 100% 拦截；死循环用例在步数上限内熔断。

### S4 评测驱动优化
- 内容：Golden Dataset（≥ 40 题，4 类）；自动评测流水线；Baseline → v1 → v2 对比；Bad Case 归类。
- 门禁：一条命令产出评测报告；KPI 达到 PRD 目标值。

### S5 加固与交付
- 内容：前端演示页；模型超时重试 / 降级；结构化日志；pytest 单测 + 集成测试；README 与 Runbook。
- 门禁：测试全绿；新机器按 README 30 分钟内可跑通。

### S6 复盘沉淀
- 内容：架构图、演示截图 / 录屏、踩坑复盘、面试问答素材。

## 文档目录约定

```text
docs/
├── 00_lifecycle.md          # 本文件：生命周期与进度看板
├── 01_PRD.md                # 产品需求
├── 02_TDD.md                # 技术设计
├── 03_metrics_glossary.yaml # 指标口径字典（语义层的“唯一事实来源”）
├── 04_data_setup.md         # S1 数据底座说明
├── 05_api_contract.md       # S2 接口契约（SSE / MCP）
├── 06_eval_report.md        # S4 评测报告
├── 07_runbook.md            # S5 运维手册
├── 08_retrospective.md      # S6 复盘
├── adr/                     # 架构决策记录（Architecture Decision Records）
└── stage_reports/           # 每阶段验收报告（做了什么 / 结果 / 遗留问题）
```

## 每阶段固定动作
1. 开工前：在 `stage_reports/Sx.md` 写明本阶段目标与验收标准。
2. 开发中：重要技术取舍写入 `adr/ADR-xxx.md`。
3. 收尾时：跑门禁检查 → 填写验收结果与遗留问题 → 更新进度看板 → `CHANGELOG.md` 记录 → Git 打 tag（如 `s1-done`）。
