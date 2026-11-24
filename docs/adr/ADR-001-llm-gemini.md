# ADR-001 · LLM 选型、地区代理限制与多提供商降级（v0.2）

- 状态：已修订（2026-11-24）
- 关联评审项：`S0_review.md` P0-1、P0-2、P1-7

## 背景
用户希望优先使用 Google Gemini 生态，同时本机位于中国大陆网络环境（依赖本地代理 `127.0.0.1:7890` 访问外网）。

## 关键事实与约束
1. **计费隔离**：Gemini App 消费者订阅与 Google AI Studio 开发者 API 独立计费；需在 AI Studio 申请 `GEMINI_API_KEY`。
2. **地区限制（关键风险）**：Gemini Developer API **不支持中国大陆地区**。若 HTTP 请求直连或代理出口节点位于不受支持地区（如中国香港或大陆节点），API 将直接返回 `400 FAILED_PRECONDITION: User location is not supported for the API use`（免费层与付费层均受限）。
3. **免费层限制与数据条款**：免费层存在严格的每分钟请求数（RPM）和每日请求数（RPD）配额，且 Google 可能将免费层请求用于产品改进，因此**严禁传入任何私密商业数据**。

## 决策
1. **明确默认型号（截至 2026-11-24，S1 入口通过 `models.list` 实测确认）**：
   - 主推理/规划/归因模型：`LLM_MODEL=gemini-3.8-flash`（兼顾推理质量与免费/低成本配额；复杂推理可切 `gemini-4-carbon`）
   - 快速节点（意图初筛 / 摘要修复）：`LLM_MODEL_FAST=gemini-3.5-flash-lite`
   - 向量模型：`EMBEDDING_MODEL=gemini-embedding-2`（统一配置输出维度 `768`）
2. **显式代理配置**：`config.py` 支持配置 `HTTPS_PROXY`（如 `http://127.0.0.1:7890`），并在 S1 第一步运行 `scripts/smoke_test_llm.py` 做地区与连通性冒烟验证。
3. **统一 `LLMProvider` 抽象与无缝降级**：
   - `GeminiProvider`：基于官方 `google-genai` SDK。
   - `OpenAICompatProvider`：基于 `openai` SDK，原生支持配置 `OPENAI_BASE_URL` / `OPENAI_API_KEY`（如 DeepSeek `deepseek-chat` 或阿里云百炼 Qwen），当代理出口触发地区封锁或日配额耗尽时，改一行环境变量即可全链路切换，零业务代码改动。

## 后果
- 彻底消除“因网络/地区封锁导致项目卡死”的单点风险。
- 评测报告（S4）必须显式记录当次实验实际使用的 Provider、模型精确 ID 与日期。
