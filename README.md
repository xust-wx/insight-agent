# Insight Agent · 自主数据分析与业务归因 Agent

基于 **Gemini + LangGraph + MCP + Docker 沙箱** 的数据分析 Agent：用自然语言提问，自动对齐指标口径、规划分析、只读取数、在沙箱中做定量归因，并输出可溯源的分析报告。

> 当前进度：**S0 需求对齐与技术设计**（见 [docs/00_lifecycle.md](docs/00_lifecycle.md)）

## 文档
| 文档 | 说明 |
| :-- | :-- |
| [00_lifecycle.md](docs/00_lifecycle.md) | 生命周期、阶段门禁、进度看板 |
| [01_PRD.md](docs/01_PRD.md) | 产品需求 |
| [02_TDD.md](docs/02_TDD.md) | 技术设计 |
| [03_metrics_glossary.yaml](docs/03_metrics_glossary.yaml) | 指标口径字典 |
| [adr/](docs/adr) | 架构决策记录 |
| [stage_reports/](docs/stage_reports) | 阶段验收报告 |

## 前置准备
1. Python 3.13、Docker Desktop、Git
2. Gemini API Key：https://aistudio.google.com/apikey → 复制 `.env.example` 为 `.env` 并填写
3. Olist 数据集：https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce → 下载 zip 放到 `data/raw/olist.zip`

## 数据许可
Olist 数据集采用 CC BY-NC-SA 4.0，仅用于学习与作品展示。
