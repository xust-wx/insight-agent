# Insight Agent · 自主数据分析与定量贡献拆解 Agent

基于 **Qwen4-Max + Qwen3.7-Text-Embedding-Flash + LangGraph + MCP + 加固 Docker 沙箱** 的生产级数据分析 Agent：用自然语言提问，自动对齐指标口径、规划多步拆解、经 AST 安全网关只读取数、在无网隔离沙箱中调用确定性统计库完成贡献拆解（加法贡献 / LMDI / PVM 结构效应），输出每个数字均可溯源的分析报告。

> 当前进度：**S1 数据底座、EDA 与语义层已完成（全部门禁全绿，准备进入 S2 MVP 骨架联调）** —— 见 [docs/00_lifecycle.md](docs/00_lifecycle.md) 与 [docs/stage_reports/S1.md](docs/stage_reports/S1.md)

## 文档导航

| 文档 | 说明 |
| :-- | :-- |
| [00_lifecycle.md](docs/00_lifecycle.md) | 开发生命周期、工期预算、评审记录与阶段门禁 |
| [01_PRD.md](docs/01_PRD.md) | 产品需求、贡献拆解方法论边界、Baseline 与量化验收 KPI |
| [02_TDD.md](docs/02_TDD.md) | 技术架构、四层 SQL 防护、预热加固沙箱、节点 Schema 与配额控制 |
| [03_metrics_glossary.yaml](docs/03_metrics_glossary.yaml) | 可执行指标口径字典、清洗规则与维度兼容矩阵 |
| [test_plan.md](docs/test_plan.md) | L1~L4 测试分层策略与 CI 门禁 |
| [security_cases.md](docs/security_cases.md) | SQL 注入（含可写 CTE）、沙箱逃逸与 Prompt 注入红队测试清单 |
| [adr/](docs/adr) | 架构决策记录（ADR-001 ~ ADR-006） |
| [stage_reports/](docs/stage_reports) | S0 阶段报告与独立技术评审报告（`S0_review.md`） |

## S1 启动前准备

1. **基础环境**：Python 3.13、Docker Desktop（确保已启动）、Git。
2. **阿里云百炼 API Key**：
   - 复制 `.env.example` 为 `.env`。
   - 填入阿里云百炼 `DASHSCOPE_API_KEY`（主模型 `qwen4-max`、向量模型 `qwen3.7-text-embedding-flash`，国内直连无需走海外代理）。
3. **Olist 公开数据集**：
   - 登录 Kaggle 下载 https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce 压缩包，放置到 `data/raw/olist.zip`。

## 开源许可与数据署名

- 本仓库源代码采用 [MIT License](LICENSE)。
- 原始数据集版权归 **Olist** 所有（[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)，遵循 **CC BY-NC-SA 4.0** 非商业与相同方式共享协议），本仓库不分发原始数据，仅用于非商业工程学习与作品展示。
