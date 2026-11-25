-- 01_schemas.sql: Extensions, 4 isolated schemas, raw Olist tables, and agent_state tables.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS olist_raw;
CREATE SCHEMA IF NOT EXISTS olist_clean;
CREATE SCHEMA IF NOT EXISTS olist_distractor;
CREATE SCHEMA IF NOT EXISTS agent_state;

-- ============================================================================
-- 1. Raw Olist Tables (mirror Kaggle CSV columns 1:1, including original typos)
-- ============================================================================

CREATE TABLE IF NOT EXISTS olist_raw.olist_customers_dataset (
    customer_id TEXT,
    customer_unique_id TEXT,
    customer_zip_code_prefix TEXT,
    customer_city TEXT,
    customer_state TEXT
);

CREATE TABLE IF NOT EXISTS olist_raw.olist_geolocation_dataset (
    geolocation_zip_code_prefix TEXT,
    geolocation_lat DOUBLE PRECISION,
    geolocation_lng DOUBLE PRECISION,
    geolocation_city TEXT,
    geolocation_state TEXT
);

CREATE TABLE IF NOT EXISTS olist_raw.olist_order_items_dataset (
    order_id TEXT,
    order_item_id INTEGER,
    product_id TEXT,
    seller_id TEXT,
    shipping_limit_date TIMESTAMP WITHOUT TIME ZONE,
    price DOUBLE PRECISION,
    freight_value DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS olist_raw.olist_order_payments_dataset (
    order_id TEXT,
    payment_sequential INTEGER,
    payment_type TEXT,
    payment_installments INTEGER,
    payment_value DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS olist_raw.olist_order_reviews_dataset (
    review_id TEXT,
    order_id TEXT,
    review_score INTEGER,
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date TIMESTAMP WITHOUT TIME ZONE,
    review_answer_timestamp TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS olist_raw.olist_orders_dataset (
    order_id TEXT,
    customer_id TEXT,
    order_status TEXT,
    order_purchase_timestamp TIMESTAMP WITHOUT TIME ZONE,
    order_approved_at TIMESTAMP WITHOUT TIME ZONE,
    order_delivered_carrier_date TIMESTAMP WITHOUT TIME ZONE,
    order_delivered_customer_date TIMESTAMP WITHOUT TIME ZONE,
    order_estimated_delivery_date TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS olist_raw.olist_products_dataset (
    product_id TEXT,
    product_category_name TEXT,
    product_name_lenght INTEGER,
    product_description_lenght INTEGER,
    product_photos_qty INTEGER,
    product_weight_g DOUBLE PRECISION,
    product_length_cm DOUBLE PRECISION,
    product_height_cm DOUBLE PRECISION,
    product_width_cm DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS olist_raw.olist_sellers_dataset (
    seller_id TEXT,
    seller_zip_code_prefix TEXT,
    seller_city TEXT,
    seller_state TEXT
);

CREATE TABLE IF NOT EXISTS olist_raw.product_category_name_translation (
    product_category_name TEXT,
    product_category_name_english TEXT
);

-- ============================================================================
-- 2. Agent State Tables (Jieba-tokenized Hybrid Index & Confirmed User Memory)
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_state.semantic_documents (
    id BIGSERIAL PRIMARY KEY,
    doc_type TEXT NOT NULL,            -- 'metric' | 'few_shot' | 'table_schema' | 'pitfall'
    doc_key TEXT NOT NULL UNIQUE,      -- e.g. 'metric:gmv', 'table:olist_clean.orders'
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tsv_tokens TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    tsv TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(tsv_tokens, ''))
    ) STORED,
    embedding vector(1024),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotent upgrade path if semantic_documents existed from earlier S1 run
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'agent_state'
          AND table_name = 'semantic_documents'
          AND column_name = 'tsv_tokens'
    ) THEN
        ALTER TABLE agent_state.semantic_documents ADD COLUMN tsv_tokens TEXT NOT NULL DEFAULT '';
        ALTER TABLE agent_state.semantic_documents ADD COLUMN content_hash TEXT NOT NULL DEFAULT '';
        ALTER TABLE agent_state.semantic_documents DROP COLUMN IF EXISTS tsv;
        ALTER TABLE agent_state.semantic_documents
            ADD COLUMN tsv TSVECTOR GENERATED ALWAYS AS (
                to_tsvector('simple', coalesce(tsv_tokens, ''))
            ) STORED;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_semantic_docs_type ON agent_state.semantic_documents (doc_type);
CREATE INDEX IF NOT EXISTS idx_semantic_docs_tsv ON agent_state.semantic_documents USING GIN (tsv);

CREATE TABLE IF NOT EXISTS agent_state.user_memory (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    metric_or_term TEXT NOT NULL,
    confirmed_rule TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_thread_id TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_user_memory_active
    ON agent_state.user_memory (user_id, metric_or_term)
    WHERE is_active = TRUE;
