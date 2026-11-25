# ADR-001 · 模型选型：阿里云百炼 Qwen4-Max + Qwen3.7-Text-Embedding-Flash（v0.3）

- 状态：已接受（2026-11-25，取代原 Gemini 主模型方案）
- 关联评审项：彻底消除 `S0_review.md` P0-1（中国大陆地区封锁风险）与 P0-2（模型与 Embedding 规格固化）

## 背景与演进
- S0 初稿曾计划采用 Google Gemini Developer API，但在技术评审中识别出两项硬约束：
  1. Gemini App 消费者订阅不含 API 额度；
  2. Gemini API 不支持中国大陆地区，高度依赖海外代理出口稳定性，存在 `FAILED_PRECONDITION: location is not supported` 断连风险。
- 经项目对齐，决定将主推理模型切换为 **`qwen4-max`**，向量模型切换为 **`qwen3.7-text-embedding-flash`**（通过阿里云百炼 DashScope OpenAI 兼容接口调用）。

## 决策与技术规范

### 1. 模型与端点定型
- **统一接入端点**：`https://dashscope.aliyuncs.com/compatible-mode/v1`（使用标准 `openai` Python `AsyncOpenAI` 客户端，环境变量 `DASHSCOPE_API_KEY`）。
- **主生成与推理模型**：`LLM_MODEL=qwen4-max`（最高 1M 上下文窗口）。
  - **分层推理预算控制（关键成本与延迟优化）**：利用 `qwen4-max` 支持的 `reasoning_effort` 参数按节点动态调节思考开销：
    - 轻量确定性节点（`Understand` 意图识别、简单 SQL 生成、`VerifyNumbers` 校对）：设 `reasoning_effort="low"`（低延迟、省思考 Token）；
    - 复杂节点（多维拆解 `Plan`、多次报错后的 SQL/Python 深度修复、`Synthesize` 综合报告）：设 `reasoning_effort="high"`。
- **向量嵌入模型**：`EMBEDDING_MODEL=qwen3.7-text-embedding-flash`
  - **向量维度**：固定采用默认高精度维度 `EMBEDDING_DIM=1024`（支持 MRL 可调 `1024/768/512/256`，PostgreSQL `pgvector` 列定义为 `vector(1024)`）。
  - **SDK 兼容性强约束**：`openai` Python SDK 在安装了 `numpy` 的环境下默认发送 `encoding_format="base64"`，而 DashScope 兼容端点要求浮点数组格式——封装层**必须显式传参 `encoding_format="float"`**。

### 2. 国内直连与系统代理旁路（防止本地代理干扰）
- 开发机开启了系统代理（`127.0.0.1:7890` 用于访问 GitHub/Docker Hub）。若国内百炼请求误走海外代理，会平白增加数百毫秒延迟甚至断连。
- **工程规则**：DashScope 客户端初始化 `httpx.AsyncClient(trust_env=False)`（或在配置中声明 `NO_PROXY=localhost,127.0.0.1,dashscope.aliyuncs.com`），确保百炼流量**国内直连**。

### 3. 多提供商兼容保留
- 由于底层直接基于标准 OpenAI Chat Completions / Embeddings 协议构建，接口天然兼容 DeepSeek、vLLM 本地服务或 Gemini OpenAI 兼容层，保留多模型横向评测能力。

## 后果
- **正面**：彻底根除地区封锁风险，国内直连低延迟，中文业务术语与口径理解能力更强，单一 `openai` SDK 即可同时驱动对话与 Embedding（减少额外 SDK 依赖）。
- **需注意**：`qwen4-max` 开启深度推理时会消耗思维链（Thinking）Token，需在 `max_completion_tokens` 与 Trace 日志中单独统计 `reasoning_tokens`，防止单题预算超支。
