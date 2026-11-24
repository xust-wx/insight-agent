# S0 阶段评审报告

- 评审日期：2026-11-24
- 评审对象：`01_PRD.md`、`02_TDD.md`、`03_metrics_glossary.yaml`、`adr/ADR-001~003`、`00_lifecycle.md`、`stage_reports/S0.md`、`.env.example`
- 结论：**有条件通过**。结构完整、方向正确；但有 **4 个阻塞项（P0）** 必须在 S1 开工前修正，否则会直接导致返工或跑不通。

## 一、总体评分

| 维度 | 评分 | 说明 |
| :-- | :-- | :-- |
| 文档结构完整性 | 8/10 | PRD / TDD / 口径 / ADR / 阶段门禁齐全 |
| 内容深度 | 6/10 | 关键设计停留在“列名词”，缺少可落地的细节（见第三节） |
| 技术可行性 | 5/10 | 地区限制、沙箱细节、SQL 安全、Olist 数据事实存在硬伤 |
| 评测可验证性 | 5/10 | KPI 先于 Baseline 拍定，且部分互相矛盾 |
| 内部一致性 | 6/10 | 状态、目录、模块职责有自相矛盾之处 |

## 二、P0 阻塞项（S1 前必须修）

### P0-1 Gemini API 在中国大陆不可用，TDD 风险表未列出
- 事实：Gemini Developer API / AI Studio **不支持中国大陆地区**，请求从不受支持的地区或出口节点发出，会返回 `User location is not supported`，免费层和付费层都一样。
- 现状：本机 `~/.gitconfig` 与系统代理（`127.0.0.1:7890`）说明你依赖代理访问外网。但 Python SDK 的流量是否走代理、**代理出口节点是否在受支持地区**，文档完全没有提及。
- 修正：
  1. S1 前先做 **连通性冒烟测试**：用 `GEMINI_API_KEY` 调一次最小请求，成功后才继续。
  2. TDD 风险表新增“API 地区限制”一条；`config.py` 支持 `HTTPS_PROXY`；Docker 拉镜像也需要代理，写进 Runbook。
  3. 备选方案：保留 OpenAI 兼容适配层（ADR-001 已提到，但 TDD 目录里没有对应抽象），可切到 DeepSeek / Qwen 作降级。

### P0-2 `.env.example` 中模型名为空，ADR-001 没有给出具体默认值
- `LLM_MODEL=`、`LLM_MODEL_FAST=` 为空；ADR-001 写“默认：较强模型 / 快速模型”却没有具体型号。模型型号和免费额度变化很快，空着就无法开发、无法复现评测。
- 修正：连通性测试通过后，用 `models.list` 取当前可用模型，在 ADR-001 中**写死具体型号 + 记录日期**；评测报告里必须记录所用模型版本。
- 同时缺少 **Embedding 模型**（见 P1-2）。

### P0-3 口径字典与 Olist 真实数据不符（会直接教坏 Agent）
对照 Olist 公开资料，发现以下问题：

| 位置 | 问题 | 修正 |
| :-- | :-- | :-- |
| `tables.reviews.key: review_id` | **`review_id` 不唯一**（约 800+ 重复，同一 review 可对应多个订单）；且一个订单可有多条评价 | 主键写成 `(review_id, order_id)`；`avg_review_score` / `bad_review_rate` 须说明以**订单粒度去重**（如取每单最新一条） |
| `category_translation` | 约 610 个商品 `product_category_name` 为 NULL，另有个别品类无英文翻译 | 品类维度表达式改为 `COALESCE(t.english, p.category, 'unknown')`，并写入 `known_pitfalls` |
| `products` 表 | 列名存在拼写错误 `product_name_lenght`、`product_description_lenght` | S1 导入时统一改名或在 Schema 元数据中显式标注，否则模型会写出 `length` 导致报错 |
| 时间字段 | CSV 导入后均为文本，且为巴西本地时间，未定义时区与月份分桶规则 | 建表时转 `timestamp`；口径中声明“按本地时间、不做时区转换” |
| `valid_order` 过滤 | 仅排除 `canceled/unavailable`，使 `created / approved / invoiced / processing / shipped` 等未完成订单计入 GMV | 在口径文档里**显式说明取舍理由**，或提供“仅 delivered”变体指标 |
| `repurchase_rate` | “统计周期内”无明确窗口；Olist 复购率仅约 3%，样本极小 | 明确定义（如：周期内首次下单用户中，在 N 天内再次下单的比例），并在 SC-6 标注“数据稀疏”风险 |
| `delivery_days`/`late_delivery_rate` | 过滤字段是裸 SQL 字符串，而其他指标引用 `valid_order` 的 ID，格式不一致 | 统一结构（见 P1-1） |
| 缺失 | 没有“指标 × 维度兼容矩阵” | 如 `payment_type` 与 GMV 同时使用会因一单多支付造成重复放大；`seller_state` 需经 `order_items`；这些必须显式化 |

### P0-4 示例问题与数据事实未核对，Golden Set 无从谈起
- PRD 与对话中的示例（如“2018-08 GMV 环比为什么下降”“2018 Q2 圣保罗州 GMV 下降”）**没有基于真实数据验证过是否存在这个现象**。2018-08 之后数据急剧稀疏，Olist 也**没有营销投放、流量、成本、促销日历**数据。
- 影响：
  1. “为什么”只能做**描述性贡献度拆解**，不能下因果结论。PRD 与演示话术必须把“归因”明确限定为 **contribution decomposition（贡献拆解）**，并让 Agent 在报告里自带“相关≠因果、缺少外部数据”的免责说明；否则面试官一追问“你怎么证明因果”就会露怯。
  2. 必须在 S1 末尾增加一步 **数据探索（EDA）**：先用人工 SQL 找出真实存在的异动月份 / 区域，再据此改写 PRD 示例与 Golden Set。
- 新增 `docs/04_data_setup.md` 时同时产出 `docs/eda_findings.md`。

## 三、P1 重要缺口（S2 前补齐）

### P1-1 口径字典不可被程序消费
- 公式是伪 SQL 字符串（`"COUNT(user WHERE orders>=2) / COUNT(user)"` 不是 SQL），无法直接喂给语义层，也无法校验。
- 建议：每个指标补充 **可执行的 SQL 模板 + 所需 join 路径 + 允许的维度列表**，并加一个 `scripts/validate_glossary.py`（S1 交付）：逐个执行模板，与人工核对值比对。

### P1-2 语义层/检索设计缺失，且与“大库”叙事矛盾
- TDD 写了 pgvector，但**没有 Embedding 模型、向量维度、切块策略、Top-K / 混合检索（BM25 + 向量）方案、召回评测方法**。
- 更根本的问题：Olist 只有 **9 张表、约 50 个字段**，整份 Schema 加口径只需约 3~5K token，直接放进 Prompt 即可，**向量召回在这个规模下没有必要**。之前对话中说的“100 张表上下文爆炸”在本数据集上并不成立。
- 建议二选一并写成 ADR：
  - A. 承认小库：Baseline = 全量 Schema 入 Prompt；检索层只用于 **口径 / Few-shot / 历史记忆**，作为 v1 的可对比优化项（用评测数据说话，效果不好就如实记录）。
  - B. 人为扩展难度：加入若干**干扰表**（如生成的 30~50 张无关业务表）以模拟真实数仓，这样召回才有评测意义。

### P1-3 沙箱设计有可运行性漏洞
- `--read-only` 与 matplotlib 冲突：需 `--tmpfs /tmp` 并设置 `MPLCONFIGDIR`；缺 `--pids-limit`、`--cap-drop ALL`、`--security-opt no-new-privileges`、非 root 用户。
- “结果落盘供沙箱读取”：MCP Server 与沙箱容器**共享目录的挂载方案没写**（Windows + Docker Desktop 的 `D:` 盘挂载路径、权限、性能需验证）。
- 每次 `docker run` 冷启动约 1~3 秒，多步分析会累积延迟；应评估**预热常驻容器 + `exec`** 或容器池。
- 内部不一致：TDD 目录把归因算法放在宿主机 `src/.../analysis/`，沙箱镜像却只装 pandas / scipy。必须明确：**归因函数打包进沙箱镜像（模型调用固定函数，不是现场写算法）**，这样更稳定、可测、可评测。

### P1-4 SQL 安全设计不够
- “仅允许单条 SELECT / WITH”不够：PostgreSQL 支持**可写 CTE**（`WITH x AS (DELETE ... RETURNING *) SELECT ...`），也有 `pg_read_file`、`pg_sleep`、`dblink`、`SELECT ... INTO`、`FOR UPDATE` 等危险点。
- 建议叠加多层防线：
  1. sqlglot 遍历整棵 AST，**出现任何 DML/DDL 节点或黑名单函数即拒绝**；
  2. 数据库侧 `ALTER ROLE ... SET default_transaction_read_only = on`，`REVOKE` 默认权限、只授 `SELECT` 到业务 schema；
  3. `statement_timeout`、`idle_in_transaction_session_timeout`；
  4. 自动加 `LIMIT` 时返回 `truncated: true` 标志，避免聚合结果被静默截断后模型误判。
- 安全测试用例清单（SQL 注入、Prompt 注入、越权）应在 S0 就列成表，S3 才有验收依据。

### P1-5 KPI 设定与评测方案有逻辑问题
- KPI 在没有 Baseline 的情况下拍定（S0 报告里也承认“待复核”），应改为：**先定义 Baseline，再设相对提升目标**。
- “单题平均 Token 成本较 Baseline 下降”与方案矛盾：反思重试、多步下钻、LLM-as-Judge 都会**增加**成本。应改为“成本在预算上限内，并报告 成本-准确率 权衡”。
- “数字幻觉率 ≤2%”**没有测量方法**：建议定义为“报告中出现的数值，能在工具输出里找到匹配项的比例”，用正则抽数 + 工具输出比对自动化。
- “平均 ≤30s”在免费层限流 + 多步 + 沙箱冷启动下不现实，应**按问题类别分档**（简单查询 ≤10s，归因 ≤60s）。
- Golden Set 的标准答案产生方式没写：必须是**人工编写并验证过的 SQL 结果**，不可由 LLM 生成；归因题的“标准答案”要定义为可数值比对的事实（如“贡献度前三的州及占比，容差 ±2%”）。
- Baseline 需精确定义：如“单次调用、全量 Schema 入 Prompt、无工具、无反思”。

### P1-6 可观测性方案过重
- Langfuse v3 自托管需要 **web + worker + PostgreSQL + ClickHouse + Redis + MinIO（S3）共 6 个容器**，官方建议本地至少 4 vCPU / 8~16GB 内存。个人笔记本上同时跑业务数据库、沙箱和评测会很吃力。
- 建议：默认使用**本地 JSONL Trace + OpenTelemetry**，Langfuse 改用云端免费版（注意 Trace 内容离开本机，Olist 为公开数据，影响不大）或 Arize Phoenix（单容器、更轻）。

### P1-7 免费层额度与隐私未做容量规划
- 免费层配额限制按项目计，且**可能用你的 Prompt/响应改进 Google 产品**。40 题 × 多步 × 3 版本 × LLM Judge 的调用量需要估算，否则评测跑到一半被限流。
- 建议：在 TDD 增加一张 **调用量预算表**；评测加缓存与断点续跑；必要时为评测绑定付费结算（小额）或降级到更小模型。

## 四、P2 一般改进

| 编号 | 问题 | 建议 |
| :-- | :-- | :-- |
| P2-1 | **HITL 触发条件在 Olist 上几乎不会触发**：数据量仅约 10 万行，“预估扫描量过大”永远不成立 | 改为**口径歧义触发**（如“GMV 是否含运费”）与“结果将用于对外结论”确认；成本阈值作为可配置项保留 |
| P2-2 | 记忆（FR-10）和上下文压缩只出现在 PRD/生命周期，**TDD 里没有设计** | 补：存储位置（Postgres 表）、写入时机（仅用户明确确认后写入）、读取方式、过期与冲突策略 |
| P2-3 | Checkpoint 后端没选（SqliteSaver / PostgresSaver） | 在 ADR 中明确；建议复用业务 Postgres 的独立 schema |
| P2-4 | 缺 API 端点清单；`interrupt` 事件需要配套“恢复接口” | S0 补一版草案：`POST /chat`、`POST /chat/{thread_id}/resume`、`GET /artifacts/{id}`、`GET /health` |
| P2-5 | 各节点 LLM 输出的**结构化 Schema** 未定义（Understand / Plan 的 JSON 结构）；Prompt 管理与版本化缺失 | 在 TDD 增加节点 I/O 表，Prompt 放 `prompts/` 并纳入版本与评测记录 |
| P2-6 | 归因方法只有两条公式 | 补充 **价格-销量-结构（PVM/Mix）效应**，避免“结构变化”被误读为“单一维度下降”（辛普森悖论）；LMDI 适用条件（值非负）需说明 |
| P2-7 | 工程规范缺失：无 `pyproject.toml`、依赖锁定、ruff / mypy / pre-commit、GitHub Actions | S2 开头补；CI 只跑不需要 LLM 的单测与 lint，LLM 相关测试用录制回放 |
| P2-8 | 许可证：项目自身无 `LICENSE`；Olist 为 **CC BY-NC-SA 4.0（相同方式共享）**，若仓库中包含由其派生的样例 / Golden Set 答案，需同样许可并署名 | 代码用 MIT，数据派生物单独目录并声明 CC BY-NC-SA；README 加 attribution |
| P2-9 | Docker 默认端口绑定与弱口令 | Compose 中端口绑定 `127.0.0.1:5432:5432`；`.env.example` 的占位密码保持占位，禁止提交真实值 |
| P2-10 | 下载渠道：Kaggle 需登录 / 代理 | 备选：`kagglehub`、Kaggle CLI；校验 SHA256 与行数写入 `04_data_setup.md` |
| P2-11 | 并发与会话：`thread_id`、产物目录生命周期与清理策略缺失 | 在 TDD 补会话与存储章节 |

## 五、内部一致性问题

1. **状态矛盾**：`00_lifecycle.md` 看板写 S0 “✅ 已完成（待评审）”，且已打 `s0-done` 标签并推送，但 `S0.md` 写“待评审”。真实情况是**没有任何评审发生**。→ 本报告出具后，把 S0 改为“🟡 评审中”，修复 P0 后再打 `s0-final` 标签。
2. **阶段 S0 门禁写“评审通过”，却没有评审人、评审记录模板**。→ 增加评审记录与遗留问题表。
3. **缺少工期估算与负责人**：生命周期只有阶段，没有人天估算与日期，无法判断进度风险。
4. **缺 `docs/eda_findings.md`、`docs/test_plan.md`、`docs/security_cases.md`** 三份关键文档。
5. 对话中我曾提到“GMV = 流量 × 转化率 × 客单价”拆解，**Olist 无流量与转化数据，做不了**；TDD 的“订单数 × 客单价”两因素才是可行的。请忽略早先的三因素说法。

## 六、可行性总判断

| 模块 | 可行性 | 备注 |
| :-- | :-- | :-- |
| Olist + PostgreSQL + 只读账号 | 高 | 数据脏点已知，可控 |
| MCP Server + FastAPI + SSE | 高 | 常规工程 |
| LangGraph 状态机 + HITL + Checkpoint | 高 | 需先定后端 |
| Docker 沙箱 | 中 | Windows 挂载 / 冷启动 / 加固参数需先做 PoC |
| Gemini 调用 | **中偏低（取决于代理出口）** | P0-1 必须先验证 |
| 向量语义层的收益 | 低（9 张表场景） | 作为可对比实验，不要作为卖点硬写 |
| “归因”的因果可信度 | 低（无外部数据） | 改称“贡献拆解”并加免责声明 |
| Langfuse 自托管 | 低（本机资源） | 降级为 JSONL + 云端 / Phoenix |
| 评测 KPI 达标 | 待定 | 先跑 Baseline 再设目标 |

## 七、修正行动清单（建议执行顺序）

| # | 动作 | 对应问题 | 产出 |
| :-- | :-- | :-- | :-- |
| 1 | 做 Gemini 连通性冒烟测试，确认代理与地区 | P0-1、P0-2 | 更新 ADR-001（具体模型 + 日期） |
| 2 | 修订 `03_metrics_glossary.yaml`（review 主键、品类空值、列名拼写、时区、复购定义、兼容矩阵、结构化 SQL 模板） | P0-3、P1-1 | v0.2 口径字典 |
| 3 | PRD 将“归因”改为“贡献拆解”，加免责声明；示例问题改为占位，待 EDA 回填 | P0-4 | PRD v0.2 |
| 4 | TDD v0.2：沙箱加固与挂载方案、SQL 多层防线、Embedding / 检索决策、记忆与会话设计、API 端点、可观测性降级、调用量预算 | P1-2~P1-7、P2 | TDD v0.2 + ADR-004~006 |
| 5 | 重写 KPI：先 Baseline 后相对目标；成本指标改预算制；幻觉率给测量方法；耗时分档 | P1-5 | PRD KPI 表 |
| 6 | 补 `test_plan.md`、`security_cases.md`；加 LICENSE；S0 状态改“评审中” | 第五节、P2-8 | 新文档 |
| 7 | S1 增加 EDA 子任务，产出 `eda_findings.md` 并回填示例与 Golden Set | P0-4 | S1 范围更新 |
| 8 | 修复完毕后打 `s0-final` 标签 | 一致性问题 1 | Git 标签 |
