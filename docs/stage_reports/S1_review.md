# S1 阶段独立技术评审报告

- 评审日期：2026-11-25
- 评审对象：S1 交付物（`infra/`、`scripts/`、`src/insight_agent/`、`tests/`、`docs/04_data_setup.md`、`docs/eda_findings.md`、`docs/stage_reports/S1.md`、`docs/03_metrics_glossary.yaml` 修订）
- 评审方法：代码与文档走查，并在真实库上执行探针脚本复核（只读角色越权、指标口径、检索质量、数据事实）。
- **评审结论：⚠️ 有条件通过**：数据导入、清洗层和 LLM 连通性都扎实可靠；但有 3 项 P0 问题说明 `S1.md` 中“强只读隔离 100%”和“混合检索就绪”两项结论**说过头了**，另有 1 个指标口径有缺陷。建议先修完 P0，再打 `s1-done` 标签。

| 级别 | 数量 | 含义 |
| :-- | :-- | :-- |
| P0 | 3 | 安全或正确性缺陷，进入 S2 前必须修复 |
| P1 | 6 | 会影响 S2–S4 质量或可信度，建议在 S1 收尾时一并修复 |
| P2 | 7 | 改进项，可以排进后续阶段 |

---

## 1. 做得好的地方（予以确认）

- **数据导入与校验**：9 张表的行数与官方 100% 一致；`COPY` 流式导入，100 万行地理表只需几秒。
- **清洗层设计落地准确**：`reviews` 按订单去重，主键唯一已由测试断言；`category_en` 无 NULL；`geolocation` 从 1,000,163 行聚合到 19,015 行，消除了 JOIN 时的行数膨胀；列名拼写已修正。
- **口径数据交叉校验能对上**：`gmv_with_freight` = 15,683,706.74，`payment_amount` = 15,687,157.17，差异仅 0.02%，说明清洗层没有放大金额。
- **LLM 客户端实测通过**：`trust_env=False` 直连生效，`reasoning_effort` 被真实接受并返回 `reasoning_tokens`，`encoding_format="float"` 返回 1024 维向量。这些都证实了 ADR-001 的假设。
- **向量召回语义合理**：以 `metric:late_delivery_rate` 为查询时，Top-3 依次是履约/差评 Few-shot（0.77）、`delivery_days`（0.73）、`bad_review_rate`（0.67）。
- **工程规范**：脚本可以重复执行；`.env` 和 `data/` 没有进入 Git；`ruff` 与 `pytest` 都通过。

---

## 2. P0 问题（必须修复）

### P0-1 只读角色的“硬隔离”能被会话级 `SET` 一键关闭

**探针实测**（以 `readonly_analyst` 登录）：

| 操作 | 结果 |
| :-- | :-- |
| `SET statement_timeout = 0` | ❌ **成功**（15s 超时兜底失效，可以发起长查询 DoS） |
| `SET default_transaction_read_only = off` | ❌ **成功**（只读事务这一层防护失效） |
| `BEGIN READ WRITE; CREATE TEMP TABLE ...` | ❌ **成功**（默认 `TEMP` 权限授给了 `PUBLIC`） |
| `SELECT ... FROM pg_catalog.pg_roles` / `information_schema.tables` | ❌ 可读（系统目录对所有角色可见，可用于 Schema 侦察） |
| `SELECT pg_sleep(...)` | ❌ 可执行 |

**分析**：`ALTER ROLE ... SET` 只设置**会话默认值**，并不是强制约束。S1 中 6 项安全测试之所以全部通过，是因为测试用例没有先执行 `SET`。目前真正拦住写操作的，只有“仅授予 SELECT 权限”这一层。TDD 中设计的“四层防护”，在数据库侧实际只剩一层半。

**修复建议**：
1. `03_readonly_role.sql` 增加 `REVOKE TEMP ON DATABASE olist FROM PUBLIC;`（同时 `REVOKE CONNECT ... FROM PUBLIC`，只向需要的角色单独 `GRANT CONNECT`）。
2. **执行器侧强制**：每条查询都包在 `BEGIN READ ONLY; SET LOCAL statement_timeout = '15s'; <sql>; ROLLBACK;` 里，不依赖角色的默认值。
3. S2 的 `sql_guard` 必须拦截 `SET` / `RESET` / `BEGIN` / `COMMIT` / `DO` / `CALL` 等所有非 `SELECT` 语句，并对 `pg_catalog`、`information_schema` 做 Schema 级拦截（`security_cases.md` SEC-SQL-07 已经要求）。
4. `validate_glossary.py` 和 `tests/integration/` 增加“先 `SET ... off` 再尝试写入或长查询”的攻击用例。
5. 修正 `S1.md` 中“100% 拦截”的表述。

### P0-2 `late_delivery_rate` 把“当天送达”误判为逾期

**探针实测**：`order_estimated_delivery_date` 的时间部分**全部是 `00:00:00`**（distinct time = 1）。口径用的是 `delivered_ts > estimated_date`，所以预计送达当天任何时刻送达的订单都会被计为逾期。

| 口径 | 逾期单数 | 逾期率 |
| :-- | --: | --: |
| 现行（时间戳比较） | 7,822 | 8.13% |
| 修正（`::date > ::date`） | 6,531 | ≈ 6.79% |
| **误判（当天送达）** | **1,291** | 偏高约 1.3 个百分点（相对高估 ~20%） |

**影响面**：`03_metrics_glossary.yaml` 的 `late_delivery_rate`、`eda_findings.md` 第 5 节（逾期 vs 准时差评率 54.05% vs 9.20%）、`01_PRD.md` SC-5 示例中的数字、Few-shot `late_delivery_vs_bad_review`，以及之后 S4 Golden Set 的标准答案。

**修复建议**：口径统一改为 `o.order_delivered_customer_date::date > o.order_estimated_delivery_date::date`，并在 `known_pitfalls` 中新增 `estimated_date_is_date_only`。然后重跑 EDA 并回填 PRD。

### P0-3 关键词检索对中文完全失效（混合检索只剩向量这一半）

**探针实测**：`to_tsvector('simple', '有效商品成交额 GMV（不含运费）')` → `'有效商品成交额' 'gmv' '不含运费'`。`simple` 解析器只按空白和标点切分，**整段中文会成为一个 token**。

| 查询词 | 命中文档数 |
| :-- | --: |
| `GMV` | 8 |
| `成交额` | **0** |

**分析**：用户的提问和口径别名大部分是中文，所以 ADR-004 中“BM25 + 向量 RRF 融合”的关键词一路实际上没有召回能力。另外，PostgreSQL 的 `ts_rank` 本身也不是 BM25，文档措辞需要修正。

**修复建议**（二选一，需要写入 ADR-004）：
- **方案 A（推荐，零扩展依赖）**：在应用层用 `jieba` 分词（同时把口径别名加入自定义词典），把空格拼接后的分词结果写入 `tsv_text` 列，再对它做 `to_tsvector('simple', ...)`；查询端走同样的分词流程。
- **方案 B**：换用带 `zhparser` / `pg_jieba` 扩展的 Postgres 镜像，代价是需要自建镜像。
- 无论选哪种方案，都要补一个中文召回单测（`成交额`、`逾期率`、`复购` 都必须命中对应指标）。

---

## 3. P1 问题（建议 S1 收尾时修复）

| 编号 | 问题 | 证据 | 建议 |
| :-- | :-- | :-- | :-- |
| P1-1 | **`olist_admin` 是超级用户**，而且 `ingest` / `build_semantic_index` 直接用它连接 | `rolsuper = true`（`POSTGRES_USER` 默认就是超级用户） | 新建 `agent_service` 角色（只能读写 `agent_state`，并对 `olist_*` 有只读权限）；超级用户只用于初始化 DDL。TDD §4 中“仅后端服务账号可读写 `agent_state`”目前没有落地 |
| P1-2 | **“指标 × 维度”组合校验没有实现** | `validate_glossary.py` 只执行了 12 条基础模板，`dimensions.*.join_sql` 和 `allowed_dimensions` 从未被执行过 | 按 `allowed_dimensions` 自动拼出 `GROUP BY` 变体并执行，同时断言：按维度拆分后求和 = 总值（可加性指标）。这是 S0 评审之后承诺过的项 |
| P1-3 | **Few-shot SQL 号称“已验证”，实际从未执行** | 3 条 Few-shot 写死在 `build_semantic_index.py` 常量里 | 移到 `eval/few_shots/*.yaml`（带版本号），由 `validate_glossary.py` 一并执行；其中逾期 Few-shot 还需要跟着 P0-2 修正 |
| P1-4 | **EDA 文档写了因果标签** | `eda_findings.md`：“最大单月正向飙升（**黑五效应**）” | 违反 PRD §1 和 R-6 的非因果原则，而且该文档会成为 Prompt 和评测素材。改为“与黑五促销时间窗重合（数据集内无促销变量，不作因果判断）” |
| P1-5 | **干扰表过于“好认”，S4 的召回压测会虚高** | 30 张表都带 `erp_`、`crm_`、`hr_`、`sys_` 等明显前缀，与电商订单语义相距很远，而且都是空表 | 至少加入 10 张**近义混淆表**（如 `orders_archive_2016`、`order_items_backup`、`customer_profiles`、`seller_ratings`、`product_reviews_raw`），并给表和列加上 `COMMENT`，让 Schema 文档具备真实的召回难度。否则 ADR-004 中 `Recall@8` 的实验结论不可信 |
| P1-6 | **文档中的事实性数字不准确** | ① `04_data_setup.md` 写“消除 ~800+ 重复评价”，实测是：`review_id` 重复 814 行、一单多评 547 单、去重实际减少 551 行，三者被混为一谈；② 口径字典 `repurchase_rate_90d` 定义仍写“全盘复购率约 3%”，实测 90 天复购率为 2.03%；③ ADR-001 没有按 S1 门禁要求写入实测结果 | 逐项修正；ADR-001 补一节“S1 实测记录”（耗时、`reasoning_tokens` 字段、向量维度） |

---

## 4. P2 改进项

1. **SHA256 只记录、没有比对**：`ingest_olist.py` 只打印哈希，没有和固定的期望值对比；`kagglehub` 也没有锁定版本。建议固定为 `olistbr/brazilian-ecommerce/versions/2`，并把 9 个哈希写成常量做断言。
2. **右删失提示**：2018-08 已送达占比为 97.5%（往期约 98.9%）。末月的履约、评价类指标会轻微偏乐观，建议在口径字典的 `sparse_periods_note` 中补充说明。
3. **还有 2 个品类没有英文翻译**：`pc_gamer` 和 `portateis_cozinha_e_preparadores_de_alimentos` 在 `category_en` 中仍是葡语，建议在清洗 SQL 中补一个手工映射。（`cool_stuff`、`pet_shop` 等品类本来就是同名映射，不算问题。）
4. **语义索引每次都全量重新嵌入**：建议加 `content_hash` 列，内容没变就跳过嵌入；文档量超过 1k 时再加 HNSW 索引。
5. **测试分层配置**：`pyproject.toml` 没有设置 `addopts = "-m 'not integration and not llm'"`，CI 直接跑 `pytest` 会因为没有数据库而失败；集成测试中写死的 `99441` 应改为引用 `EXPECTED_FILES` 常量。
6. **基础设施**：`docker-compose.yml` 中管理员密码有一个弱默认值（`insight_local_admin_2026`），建议改成 `${PG_ADMIN_PASSWORD:?required}`，强制必须配置；本机使用 Hyper-V 后端时内存不足导致过启动失败，建议在 Runbook 中写明改用 WSL2 后端。
7. **`.gitignore` 的反选规则无效**：规则 `data/` 已经忽略了整个目录，`!data/.gitkeep` 不会生效（`git check-ignore` 已确认）。目前文件只是因为历史上提交过才被跟踪。应改为 `data/*` 加 `!data/.gitkeep`。

---

## 5. 门禁结论重判

| S1 门禁 | 原结论 | 评审后结论 |
| :-- | :-- | :-- |
| LLM 连通性返回 200，实际型号写入 ADR-001 | ✅ | ⚠️ 连通性通过；ADR-001 没有更新（P1-6） |
| 一键启动；9 表行数一致；`validate_glossary.py` 全绿 | ✅ | ⚠️ 全绿，但只覆盖了基础模板（P1-2），而且有 1 个口径存在缺陷（P0-2） |
| 只读账号执行 DML/DDL、可写 CTE、系统函数均被拒绝 | ✅ | ❌ **会话 `SET` 可以绕过超时与只读，系统目录可读**（P0-1） |
| `eda_findings.md` 完成真实异动事实归档 | ✅ | ⚠️ 事实基本准确；逾期一节受 P0-2 影响，且带有因果措辞（P1-4） |
| 混合检索索引（S1 内容第 6 项） | ✅ | ❌ **中文关键词召回为 0**（P0-3） |

## 6. 建议的修复顺序（预计 0.5 人天）

1. P0-1 只读加固（SQL 和执行器约定）+ 补攻击测试 → 2. P0-2 逾期口径修正 → 重跑 EDA → 回填 PRD → 3. P0-3 引入 `jieba` 分词并重建索引，补中文召回测试 → 4. P1-1 到 P1-6 → 5. 全量重跑 `ingest → validate → eda → index → pytest`，更新 `S1.md`，打 `s1-done` 标签。

> 复现脚本：`scratch/s1_review_probe.py`（只读探针，不修改任何数据）。
