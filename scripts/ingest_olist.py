"""S1 Data Ingestion: Download/extract Olist CSVs, assert SHA256 & row counts, build olist_clean & hard distractors."""

from __future__ import annotations

import hashlib
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg import sql

from insight_agent.config import PROJECT_ROOT, get_settings
from insight_agent.db.constants import (
    KAGGLE_DATASET_HANDLE,
)
from insight_agent.db.constants import (
    OLIST_EXPECTED_FILES as EXPECTED_FILES,
)

# 30 distractor tables including 12 high-confusion near-synonym e-commerce tables (P1-5 fix)
DISTRACTOR_TABLES: list[tuple[str, str, str]] = [
    # --- 12 Near-synonym high-confusion e-commerce tables ---
    (
        "orders_archive_2015",
        "order_id TEXT PRIMARY KEY, customer_id TEXT, order_status TEXT, order_purchase_timestamp TIMESTAMP, legacy_gmv NUMERIC(12,2)",
        "2015年历史迁移归档订单表（非现行分析期数据，存在旧系统状态码）",
    ),
    (
        "order_items_staging",
        "staging_id BIGSERIAL PRIMARY KEY, order_id TEXT, product_id TEXT, seller_id TEXT, raw_price NUMERIC(10,2), freight_estimate NUMERIC(10,2)",
        "订单明细ETL临时缓冲表（未去重未校验，不可用于正式GMV统计）",
    ),
    (
        "order_payments_reconciliation",
        "recon_id TEXT PRIMARY KEY, order_id TEXT, payment_type TEXT, gateway_amount NUMERIC(12,2), diff_amount NUMERIC(10,2), recon_date DATE",
        "支付网关日终对账差异表（仅记录渠道异常流水，非全量支付）",
    ),
    (
        "customer_profiles_crm",
        "profile_id TEXT PRIMARY KEY, customer_unique_id TEXT, lifecycle_tier TEXT, marketing_opt_in BOOLEAN, customer_state TEXT, updated_at TIMESTAMP",
        "CRM会员营销画像表（仅含订阅营销通知的子集用户）",
    ),
    (
        "seller_performance_monthly",
        "stat_month DATE, seller_id TEXT, seller_state TEXT, listed_skus INT, warning_points INT, PRIMARY KEY (stat_month, seller_id)",
        "商家运营考核月度评分卡（平台规则扣分表，不含交易订单明细）",
    ),
    (
        "product_reviews_moderation",
        "moderation_id TEXT PRIMARY KEY, review_id TEXT, order_id TEXT, spam_flag BOOLEAN, auto_score INT, reviewed_at TIMESTAMP",
        "评价反垃圾审核队列日志（含被拦截垃圾评论，非正式评价表）",
    ),
    (
        "product_catalog_drafts",
        "draft_id TEXT PRIMARY KEY, product_id TEXT, category_en TEXT, suggested_price NUMERIC(10,2), approval_status TEXT",
        "卖家待上架商品草稿箱（未正式开售商品）",
    ),
    (
        "shipping_freight_quotes",
        "quote_id BIGSERIAL PRIMARY KEY, customer_zip_code_prefix TEXT, seller_state TEXT, quoted_freight NUMERIC(10,2), quoted_days INT, created_at TIMESTAMP",
        "结账页运费试算询价日志（含大量未下单试算记录）",
    ),
    (
        "gmv_daily_board_deprecated",
        "stat_date DATE PRIMARY KEY, gross_orders INT, gross_gmv NUMERIC(14,2), cancelled_gmv NUMERIC(14,2)",
        "已废弃旧版BI日报汇总表（含取消单且2018年停更，严禁用于口径计算）",
    ),
    (
        "refund_disputes",
        "dispute_id TEXT PRIMARY KEY, order_id TEXT, customer_id TEXT, refund_amount NUMERIC(10,2), dispute_reason TEXT, opened_at TIMESTAMP",
        "售后退款争议工单表（客服手工登记样本）",
    ),
    (
        "cart_abandonment_events",
        "event_id BIGSERIAL PRIMARY KEY, session_id TEXT, customer_unique_id TEXT, product_id TEXT, cart_price NUMERIC(10,2), abandoned_at TIMESTAMP",
        "购物车加购未支付流失埋点日志",
    ),
    (
        "checkout_sessions",
        "session_id TEXT PRIMARY KEY, customer_state TEXT, payment_type_selected TEXT, step_reached TEXT, started_at TIMESTAMP",
        "收银台会话漏斗日志",
    ),
    # --- 18 Enterprise surrounding warehouse tables ---
    ("warehouse_stock_batches", "batch_id TEXT PRIMARY KEY, product_id TEXT, warehouse_state TEXT, qty_on_hand INT, received_at TIMESTAMP", "仓储物理批次库存表"),
    ("warehouse_inventory_snapshots", "snapshot_id BIGSERIAL PRIMARY KEY, snapshot_date DATE, warehouse_code TEXT, sku_code TEXT, stock_qty INT", "每日零点仓库库存快照表"),
    ("procurement_purchase_orders", "po_id TEXT PRIMARY KEY, supplier_id TEXT, created_at TIMESTAMP, total_cost NUMERIC(12,2), status TEXT", "自营包材采购订单表"),
    ("procurement_suppliers", "supplier_id TEXT PRIMARY KEY, supplier_name TEXT, state_code TEXT, lead_time_days INT", "包材与物流供应商名录"),
    ("crm_support_tickets", "ticket_id TEXT PRIMARY KEY, order_id TEXT, category TEXT, priority TEXT, created_at TIMESTAMP, resolved_at TIMESTAMP", "客服进线咨询工单表"),
    ("crm_nps_surveys", "survey_id TEXT PRIMARY KEY, customer_unique_id TEXT, nps_score INT, comment TEXT, submitted_at TIMESTAMP", "季度品牌NPS抽样问卷表"),
    ("crm_loyalty_points", "ledger_id BIGSERIAL PRIMARY KEY, customer_unique_id TEXT, points_delta INT, source TEXT, created_at TIMESTAMP", "会员积分变动流水表"),
    ("mkt_coupon_batches", "coupon_batch_id TEXT PRIMARY KEY, discount_pct NUMERIC(5,2), max_uses INT, valid_from DATE, valid_to DATE", "优惠券批次配置表"),
    ("mkt_coupon_redemptions", "redemption_id BIGSERIAL PRIMARY KEY, coupon_batch_id TEXT, order_id TEXT, discount_amount NUMERIC(10,2), used_at TIMESTAMP", "优惠券核销记录表"),
    ("mkt_affiliate_payouts", "payout_id TEXT PRIMARY KEY, partner_id TEXT, period_month DATE, commission_brl NUMERIC(12,2), paid BOOLEAN", "联盟客分佣结算单"),
    ("fin_gl_accounts", "account_code TEXT PRIMARY KEY, account_name TEXT, account_type TEXT", "财务总账会计科目表"),
    ("fin_tax_rates_by_state", "state_code TEXT PRIMARY KEY, icms_rate NUMERIC(5,4), iss_rate NUMERIC(5,4), effective_from DATE", "巴西各州ICMS流转税率维表"),
    ("fin_chargebacks", "chargeback_id TEXT PRIMARY KEY, order_id TEXT, reason_code TEXT, amount_brl NUMERIC(12,2), disputed_at TIMESTAMP", "信用卡拒付追偿表"),
    ("fin_settlement_batches", "settlement_id TEXT PRIMARY KEY, seller_id TEXT, settled_at TIMESTAMP, gross_amount NUMERIC(14,2), fee_amount NUMERIC(12,2)", "商家货款周期结算批次表"),
    ("ops_carrier_sla_contracts", "contract_id TEXT PRIMARY KEY, carrier_name TEXT, origin_state TEXT, dest_state TEXT, promised_days INT", "承运商干线时效合同表"),
    ("ops_package_scans", "scan_id BIGSERIAL PRIMARY KEY, order_id TEXT, hub_city TEXT, scan_type TEXT, scanned_at TIMESTAMP", "包裹分拨中心路由扫描表"),
    ("sys_audit_logs", "log_id BIGSERIAL PRIMARY KEY, actor TEXT, action TEXT, target TEXT, logged_at TIMESTAMP", "后台系统操作审计日志"),
    ("sys_batch_job_runs", "run_id BIGSERIAL PRIMARY KEY, job_name TEXT, status TEXT, started_at TIMESTAMP, finished_at TIMESTAMP", "数仓定时调度任务运行记录"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_olist_csvs(raw_dir: Path, extracted_dir: Path) -> Path:
    """Locate, extract, or download pinned Olist v2 CSV files."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    if all((extracted_dir / fname).exists() for fname in EXPECTED_FILES):
        print(f"[INFO] Found all 9 CSVs in {extracted_dir}")
        return extracted_dir

    zip_candidates = list(raw_dir.glob("*.zip"))
    if zip_candidates:
        zip_path = zip_candidates[0]
        print(f"[INFO] Extracting {zip_path} -> {extracted_dir}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extracted_dir)
        for fname in EXPECTED_FILES:
            if not (extracted_dir / fname).exists():
                found = list(extracted_dir.rglob(fname))
                if found:
                    shutil.copy2(found[0], extracted_dir / fname)
        if all((extracted_dir / fname).exists() for fname in EXPECTED_FILES):
            return extracted_dir

    print(f"[INFO] Auto-downloading pinned Kaggle dataset {KAGGLE_DATASET_HANDLE}...")
    import kagglehub

    dl_path = Path(kagglehub.dataset_download(KAGGLE_DATASET_HANDLE))
    for fname in EXPECTED_FILES:
        src = dl_path / fname
        if not src.exists():
            matches = list(dl_path.rglob(fname))
            if not matches:
                raise FileNotFoundError(f"Expected file {fname} missing in {dl_path}")
            src = matches[0]
        shutil.copy2(src, extracted_dir / fname)
    return extracted_dir


def run_sql_file(
    conn: psycopg.Connection, path: Path, replacements: dict[str, str] | None = None
) -> None:
    sql = path.read_text(encoding="utf-8")
    if replacements:
        for k, v in replacements.items():
            sql = sql.replace(k, v)
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def rebuild_distractor_tables(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS olist_distractor CASCADE;")
        cur.execute("CREATE SCHEMA olist_distractor;")
        for tbl_name, cols_ddl, comment_str in DISTRACTOR_TABLES:
            cur.execute(f"CREATE TABLE olist_distractor.{tbl_name} ({cols_ddl});")
            cur.execute(
                sql.SQL("COMMENT ON TABLE olist_distractor.{} IS {};").format(
                    sql.Identifier(tbl_name),
                    sql.Literal(comment_str),
                )
            )
        # Seed realistic synthetic rows in high-confusion tables so they aren't trivially empty
        cur.execute(
            """
            INSERT INTO olist_distractor.orders_archive_2015 VALUES
                ('arch_001', 'cust_old_1', 'delivered', '2015-11-20 10:00:00', 189.90),
                ('arch_002', 'cust_old_2', 'canceled', '2015-12-05 14:30:00', 59.00);
            INSERT INTO olist_distractor.gmv_daily_board_deprecated VALUES
                ('2017-11-24', 1150, 179000.00, 8200.00),
                ('2017-11-25', 520, 74000.00, 3100.00);
            INSERT INTO olist_distractor.order_items_staging (order_id, product_id, seller_id, raw_price, freight_estimate)
            VALUES ('stg_ord_1', 'prod_x', 'sell_x', 99.90, 15.20);
            """
        )
    conn.commit()
    return len(DISTRACTOR_TABLES)


def main() -> int:
    settings = get_settings()
    csv_dir = ensure_olist_csvs(settings.data_raw_dir, settings.data_extracted_dir)

    db_dir = PROJECT_ROOT / "infra" / "db"
    stats_rows: list[tuple[str, str, int, int, str, bool]] = []

    with psycopg.connect(settings.pg_admin_dsn) as conn:
        print("[1/5] Ensuring schemas and state table migrations (01_schemas.sql)...")
        run_sql_file(conn, db_dir / "01_schemas.sql")

        print("[2/5] Verifying SHA256 & loading 9 Olist CSVs into olist_raw via COPY...")
        for fname, (table_name, expected_rows, expected_sha256) in EXPECTED_FILES.items():
            csv_path = csv_dir / fname
            file_hash = sha256_file(csv_path)
            hash_ok = file_hash == expected_sha256
            if not hash_ok:
                raise RuntimeError(
                    f"SHA256 mismatch for {fname}: expected {expected_sha256}, got {file_hash}"
                )
            with conn.cursor() as cur:
                cur.execute(f"TRUNCATE TABLE olist_raw.{table_name};")
                with csv_path.open("r", encoding="utf-8") as f:
                    with cur.copy(
                        f"COPY olist_raw.{table_name} FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')"
                    ) as copy:
                        while data := f.read(1024 * 1024):
                            copy.write(data)
                cur.execute(f"SELECT COUNT(*) FROM olist_raw.{table_name};")
                actual_rows = int(cur.fetchone()[0])
            conn.commit()
            if actual_rows != expected_rows:
                raise RuntimeError(
                    f"Row count mismatch for {table_name}: expected {expected_rows}, got {actual_rows}"
                )
            print(
                f"  - {table_name:36s}: {actual_rows:>10,d} rows [ROW+SHA256 OK] {file_hash[:12]}..."
            )
            stats_rows.append((fname, table_name, actual_rows, expected_rows, file_hash, hash_ok))

        print("[3/5] Building cleaned analytical layer olist_clean (02_clean_views.sql)...")
        run_sql_file(conn, db_dir / "02_clean_views.sql")

        clean_counts: list[tuple[str, int]] = []
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'olist_clean'
                ORDER BY table_name;
                """
            )
            for (tbl,) in cur.fetchall():
                cur.execute(f"SELECT COUNT(*) FROM olist_clean.{tbl};")
                cnt = int(cur.fetchone()[0])
                clean_counts.append((tbl, cnt))
                print(f"  - olist_clean.{tbl:26s}: {cnt:>10,d} rows")

            cur.execute(
                """
                SELECT
                    (SELECT COUNT(*) - COUNT(DISTINCT review_id) FROM olist_raw.olist_order_reviews_dataset),
                    (SELECT COUNT(*) FROM (SELECT order_id FROM olist_raw.olist_order_reviews_dataset GROUP BY 1 HAVING COUNT(*) > 1) t),
                    (SELECT COUNT(*) FROM olist_raw.olist_order_reviews_dataset) - (SELECT COUNT(*) FROM olist_clean.reviews);
                """
            )
            dup_rev_id_rows, multi_rev_orders, dedup_removed = cur.fetchone()

        print("[4/5] Rebuilding 30 realistic distractor tables (incl. 12 near-synonyms)...")
        distractor_count = rebuild_distractor_tables(conn)
        print(f"  - Created {distractor_count} distractor tables with comments & sample rows.")

        print("[5/5] Applying 3-tier least-privilege roles (03_readonly_role.sql)...")
        run_sql_file(
            conn,
            db_dir / "03_readonly_role.sql",
            replacements={
                "__DB_NAME__": settings.pg_db,
                "__RO_USER__": settings.pg_readonly_user,
                "__RO_PASSWORD__": settings.pg_readonly_password,
                "__SVC_USER__": settings.pg_service_user,
                "__SVC_PASSWORD__": settings.pg_service_password,
            },
        )
        print(
            f"  - Roles '{settings.pg_readonly_user}' (RO, no TEMP, no sleep) & "
            f"'{settings.pg_service_user}' (NOSUPERUSER service) enforced."
        )

    doc_path = PROJECT_ROOT / "docs" / "04_data_setup.md"
    lines = [
        "# 04 · 数据底座与清洗治理报告（S1 修订版）",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- 数据库实例：PostgreSQL 16 + `pgvector`（`127.0.0.1:5432`，数据库 `olist`）",
        f"- 数据源：Kaggle `{KAGGLE_DATASET_HANDLE}`（CC BY-NC-SA 4.0，固定版本 v2 + SHA256 硬断言）",
        "",
        "## 1. 原始数据导入与哈希校验（`olist_raw`）",
        "",
        "| CSV 文件 | 表名 | 实测行数 | 官方行数 | 行数与哈希校验 | SHA256（前 16 位） |",
        "| :-- | :-- | --: | --: | :-- | :-- |",
    ]
    for fname, tbl, actual, expected, h, ok in stats_rows:
        mark = "✅ 行数+SHA256 一致" if ok and actual == expected else "❌ 异常"
        lines.append(f"| `{fname}` | `{tbl}` | {actual:,d} | {expected:,d} | {mark} | `{h[:16]}` |")

    rules_map = {
        "category_translation": "补充 `pc_gamer` 与 `portable_kitchen_food_preparers` 2 项缺失翻译（71 → 73 行）",
        "customers": "建立 `customer_unique_id` 与 `customer_state` 索引",
        "geolocation_zip_prefix": "按 5 位邮编前缀聚合经纬度均值与州/市众数（1,000,163 → 19,015 行，防 JOIN 笛卡尔积）",
        "order_items": "联合主键 `(order_id, order_item_id)`，建商品/卖家索引",
        "order_reviews_all": "保留原始全量 99,224 条评价明细供审计核查",
        "orders": "时间戳与状态清洗，建 `order_purchase_timestamp` / `order_status` 索引",
        "payments": "联合主键 `(order_id, payment_sequential)`",
        "products": "修正 `product_name_length` 拼写；610 个 NULL 品类兜底为 `'uncategorized'`，英文映射覆盖率 100%",
        "reviews": (
            f"按 `order_id` 取最新评价去重（原始表含 `review_id` 重复 {dup_rev_id_rows} 行、"
            f"一单多评 {multi_rev_orders} 单，去重实际减少 {dedup_removed} 行：99,224 → 98,673）"
        ),
        "sellers": "主键 `seller_id`，建 `seller_state` 索引",
    }

    lines.extend(
        [
            "",
            "## 2. 标准化分析层（`olist_clean`）",
            "",
            "| 清洗表名 | 行数 | 核心治理规则与实测核对 |",
            "| :-- | --: | :-- |",
        ]
    )
    for tbl, cnt in clean_counts:
        lines.append(f"| `olist_clean.{tbl}` | {cnt:,d} | {rules_map.get(tbl, '')} |")

    lines.extend(
        [
            "",
            "## 3. 三级最小权限隔离与近义混淆压测集",
            "- **三级账号分离**：",
            f"  1. `{settings.pg_admin_user}`（Superuser）：仅限离线初始化与入库脚本使用，业务运行时禁用；",
            f"  2. `{settings.pg_service_user}`（`NOSUPERUSER`）：后端应用服务账号，仅对 `agent_state` 有读写权限，对 `olist_clean`/`olist_distractor` 仅只读，不可访问 `olist_raw`；",
            f"  3. `{settings.pg_readonly_user}`（`NOSUPERUSER`）：Agent SQL 工具专用账号，回收 `TEMP` 建表与 `pg_sleep` 执行权，配合 `sql_guard` 全语法树白名单与 `ReadonlyExecutor` 逐事务 `BEGIN TRANSACTION READ ONLY` + `SET LOCAL statement_timeout = '15000ms'` 双重锁定，彻底封死会话级 `SET` 绕过。",
            f"- **高混淆度干扰压测表（`olist_distractor`）**：共 **{distractor_count} 张**表（含 `orders_archive_2015`、`order_items_staging`、`gmv_daily_board_deprecated`、`product_reviews_moderation` 等 12 张电商近义混淆表 + 完整表注释与样本行），保障 S4 `Recall@8` 评测真实可信。",
            "",
        ]
    )
    doc_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[PASS] Ingestion complete. Report saved to {doc_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
