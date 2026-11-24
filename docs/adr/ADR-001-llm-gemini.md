# ADR-001 · LLM 选型：Gemini API

- 状态：已接受（2026-11-24）

## 背景
用户已有 Gemini 订阅，希望复用。

## 关键事实
- **Gemini App 的消费者订阅（Google One AI 会员等）不包含开发者 API 调用额度**，二者计费体系独立。
- 程序调用需在 **Google AI Studio**（https://aistudio.google.com/apikey）创建 API Key；AI Studio 提供免费层（有速率限制），超出后按量付费或绑定结算账号。

## 决策
- 使用官方 `google-genai` SDK，Key 从环境变量 `GEMINI_API_KEY` 读取。
- 模型名通过 `LLM_MODEL` / `LLM_MODEL_FAST` 配置，不在代码中硬编码；默认：规划与归因用较强模型，SQL 修复 / 摘要等用快速模型。
- LLM 访问封装在 `src/insight_agent/llm/`，保留切换到其他 OpenAI 兼容服务的可能。

## 后果
- 免费层限流 → 必须实现指数退避重试、评测并发可调。
- 代码与模型厂商解耦，后续可做多模型对比评测。
