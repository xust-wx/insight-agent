# 04 · 数据底座与清洗治理报告（S1 修订版）

- 生成时间：2026-11-25 10:40:11
- 数据库实例：PostgreSQL 16 + `pgvector`（`127.0.0.1:5432`，数据库 `olist`）
- 数据源：Kaggle `olistbr/brazilian-ecommerce/versions/2`（CC BY-NC-SA 4.0，固定版本 v2 + SHA256 硬断言）

## 1. 原始数据导入与哈希校验（`olist_raw`）

| CSV 文件 | 表名 | 实测行数 | 官方行数 | 行数与哈希校验 | SHA256（前 16 位） |
| :-- | :-- | --: | --: | :-- | :-- |
| `olist_customers_dataset.csv` | `olist_customers_dataset` | 99,441 | 99,441 | ✅ 行数+SHA256 一致 | `983a422239e1712d` |
| `olist_geolocation_dataset.csv` | `olist_geolocation_dataset` | 1,000,163 | 1,000,163 | ✅ 行数+SHA256 一致 | `b514f6fc991b9566` |
| `olist_order_items_dataset.csv` | `olist_order_items_dataset` | 112,650 | 112,650 | ✅ 行数+SHA256 一致 | `0bc4d068c4fe38cb` |
| `olist_order_payments_dataset.csv` | `olist_order_payments_dataset` | 103,886 | 103,886 | ✅ 行数+SHA256 一致 | `4f713964f2815dbb` |
| `olist_order_reviews_dataset.csv` | `olist_order_reviews_dataset` | 99,224 | 99,224 | ✅ 行数+SHA256 一致 | `012b61c7593e34f5` |
| `olist_orders_dataset.csv` | `olist_orders_dataset` | 99,441 | 99,441 | ✅ 行数+SHA256 一致 | `8df58ef3d2d7e994` |
| `olist_products_dataset.csv` | `olist_products_dataset` | 32,951 | 32,951 | ✅ 行数+SHA256 一致 | `3e6569628a17fbc7` |
| `olist_sellers_dataset.csv` | `olist_sellers_dataset` | 3,095 | 3,095 | ✅ 行数+SHA256 一致 | `1f643d2b950373b8` |
| `product_category_name_translation.csv` | `product_category_name_translation` | 71 | 71 | ✅ 行数+SHA256 一致 | `a81f0d1f27b27e72` |

## 2. 标准化分析层（`olist_clean`）

| 清洗表名 | 行数 | 核心治理规则与实测核对 |
| :-- | --: | :-- |
| `olist_clean.category_translation` | 73 | 补充 `pc_gamer` 与 `portable_kitchen_food_preparers` 2 项缺失翻译（71 → 73 行） |
| `olist_clean.customers` | 99,441 | 建立 `customer_unique_id` 与 `customer_state` 索引 |
| `olist_clean.geolocation_zip_prefix` | 19,015 | 按 5 位邮编前缀聚合经纬度均值与州/市众数（1,000,163 → 19,015 行，防 JOIN 笛卡尔积） |
| `olist_clean.order_items` | 112,650 | 联合主键 `(order_id, order_item_id)`，建商品/卖家索引 |
| `olist_clean.order_reviews_all` | 99,224 | 保留原始全量 99,224 条评价明细供审计核查 |
| `olist_clean.orders` | 99,441 | 时间戳与状态清洗，建 `order_purchase_timestamp` / `order_status` 索引 |
| `olist_clean.payments` | 103,886 | 联合主键 `(order_id, payment_sequential)` |
| `olist_clean.products` | 32,951 | 修正 `product_name_length` 拼写；610 个 NULL 品类兜底为 `'uncategorized'`，英文映射覆盖率 100% |
| `olist_clean.reviews` | 98,673 | 按 `order_id` 取最新评价去重（原始表含 `review_id` 重复 814 行、一单多评 547 单，去重实际减少 551 行：99,224 → 98,673） |
| `olist_clean.sellers` | 3,095 | 主键 `seller_id`，建 `seller_state` 索引 |

## 3. 三级最小权限隔离与近义混淆压测集
- **三级账号分离**：
  1. `olist_admin`（Superuser）：仅限离线初始化与入库脚本使用，业务运行时禁用；
  2. `agent_service`（`NOSUPERUSER`）：后端应用服务账号，仅对 `agent_state` 有读写权限，对 `olist_clean`/`olist_distractor` 仅只读，不可访问 `olist_raw`；
  3. `readonly_analyst`（`NOSUPERUSER`）：Agent SQL 工具专用账号，回收 `TEMP` 建表与 `pg_sleep` 执行权，配合 `sql_guard` 全语法树白名单与 `ReadonlyExecutor` 逐事务 `BEGIN TRANSACTION READ ONLY` + `SET LOCAL statement_timeout = '15000ms'` 双重锁定，彻底封死会话级 `SET` 绕过。
- **高混淆度干扰压测表（`olist_distractor`）**：共 **30 张**表（含 `orders_archive_2015`、`order_items_staging`、`gmv_daily_board_deprecated`、`product_reviews_moderation` 等 12 张电商近义混淆表 + 完整表注释与样本行），保障 S4 `Recall@8` 评测真实可信。
