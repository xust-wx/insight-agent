# ADR-006 · 轻量化可观测性方案（替代重型自托管 Langfuse v3）

- 状态：已接受（2026-11-24）
- 关联评审项：`S0_review.md` P1-6

## 背景
Langfuse v3/v4 自托管架构依赖 `web + worker + PostgreSQL + ClickHouse + Redis + MinIO` 共 6 个容器，单机常驻内存开销达 8~16GB，在个人开发机上与业务 Postgres、Docker 沙箱及评测脚本同跑极易触发内存瓶颈。

## 决策
1. **默认主方案（零额外容器开销）**：内置结构化 **JSONL Trace 记录器 + OpenTelemetry Span 埋点**，每次运行在 `traces/YYYY-MM-DD/<trace_id>.jsonl` 完整记录每个节点的输入摘要、Prompt 版本、SQL/Python 代码、耗时、Token 用量与错误栈；评测器可直接聚合分析 JSONL 文件。
2. **可选可视化 UI（二选一，按需开启）**：
   - Docker Compose `observability` profile 提供单容器 **Arize Phoenix**（接收 OTel 协议，内存占用 `< 500MB`）；
   - 或配置环境变量接入 **Langfuse Cloud 免费版**（Olist 为公开数据集，无商业泄密风险）。

## 后果
- 开发机日常只需运行 **2 个轻量容器**（PostgreSQL + 预热沙箱 Worker），启动快、内存占用 `< 1GB`，同时保留完整的生产级 OpenTelemetry 追踪能力。
