# ADR-002 · 数据集治理与开源许可边界：Olist（v0.2）

- 状态：已修订（2026-11-24）
- 关联评审项：`S0_review.md` P0-3、P0-4、P2-8、P2-10

## 决策
使用 Kaggle 公开数据集 `olistbr/brazilian-ecommerce`（CC BY-NC-SA 4.0），并在入库时实施**双层 Schema 治理（`olist_raw` + `olist_clean`）**。

## 针对真实数据脏点的治理规则
1. **评价重复（`review_id` ~800+ 重复及一单多评）**：`olist_clean.reviews` 按 `order_id` 取最新评价去重，防止关联订单时行数与金额膨胀。
2. **品类缺失与葡语映射（~610 行 NULL 及部分未翻译）**：`olist_clean.products` 预生成 `category_en = COALESCE(en, pt, 'uncategorized')`。
3. **原始列名拼写错误（`product_name_lenght`）**：在 `olist_clean.products` 中标准化为 `product_name_length` / `product_description_length`。
4. **邮编多对多膨胀**：提供预聚合视图 `olist_clean.geolocation_zip_prefix`。
5. **因果边界**：数据不含流量、广告与促销日历，所有分析结论严格限定为**定量贡献拆解（Contribution Decomposition）**。

## 获取、校验与许可合规
- 支持手动放置 `data/raw/olist.zip` 或通过 `kagglehub` / Kaggle CLI 下载；`scripts/ingest_olist.py` 校验各 CSV 行数与文件哈希并写入 `docs/04_data_setup.md`。
- **许可证隔离**：项目工程代码采用 **MIT License**；原始数据不入库，由 Olist 派生的 Golden Set 标准答案与统计摘要在 `eval/golden_set/README.md` 与根目录 `LICENSE` 中显式署名并遵循 **CC BY-NC-SA 4.0**。
