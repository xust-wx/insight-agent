# ADR-003 · 编排框架：LangGraph + MCP

- 状态：已接受（2026-11-24）

## 备选
| 方案 | 优点 | 缺点 |
| :-- | :-- | :-- |
| 手写循环 | 透明、零依赖 | Checkpoint、中断恢复需自研 |
| LangGraph | 显式状态图、Checkpoint、`interrupt` 原生 HITL | 学习成本 |
| CrewAI / 多 Agent 框架 | 多角色上手快 | 控制粒度粗，本场景单 Agent + 工具即可 |

## 决策
LangGraph 作为运行时；数据工具以 MCP Server 暴露，Agent 通过 MCP Client 调用。

## 后果
- 状态与节点边界清晰，便于单测与评测定位 Bad Case 所在环节。
- 工具层可被其他 MCP 客户端（如 IDE Agent）复用。
