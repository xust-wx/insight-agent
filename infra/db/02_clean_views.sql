-- 02_clean_views.sql: Build cleaned, indexed analytical tables in olist_clean from olist_raw.
-- Idempotent: drops and recreates olist_clean tables after raw ingestion.

DROP TABLE IF EXISTS olist_clean.order_items CASCADE;
DROP TABLE IF EXISTS olist_clean.payments CASCADE;
DROP TABLE IF EXISTS olist_clean.reviews CASCADE;
DROP TABLE IF EXISTS olist_clean.order_reviews_all CASCADE;
DROP TABLE IF EXISTS olist_clean.orders CASCADE;
DROP TABLE IF EXISTS olist_clean.customers CASCADE;
DROP TABLE IF EXISTS olist_clean.products CASCADE;
DROP TABLE IF EXISTS olist_clean.sellers CASCADE;
DROP TABLE IF EXISTS olist_clean.geolocation_zip_prefix CASCADE;
DROP TABLE IF EXISTS olist_clean.category_translation CASCADE;

-- 1. Category translation (supplement 2 missing official translations in Olist CSV)
CREATE TABLE olist_clean.category_translation AS
SELECT
    TRIM(product_category_name) AS product_category_name,
    TRIM(product_category_name_english) AS product_category_name_english
FROM olist_raw.product_category_name_translation
UNION
SELECT 'pc_gamer', 'pc_gamer'
UNION
SELECT 'portateis_cozinha_e_preparadores_de_alimentos', 'portable_kitchen_food_preparers';

ALTER TABLE olist_clean.category_translation
    ADD PRIMARY KEY (product_category_name);

-- 2. Customers
CREATE TABLE olist_clean.customers AS
SELECT
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix,
    TRIM(customer_city) AS customer_city,
    TRIM(customer_state) AS customer_state
FROM olist_raw.olist_customers_dataset;

ALTER TABLE olist_clean.customers
    ADD PRIMARY KEY (customer_id);
CREATE INDEX idx_clean_customers_unique ON olist_clean.customers (customer_unique_id);
CREATE INDEX idx_clean_customers_state ON olist_clean.customers (customer_state);

-- 3. Sellers
CREATE TABLE olist_clean.sellers AS
SELECT
    seller_id,
    seller_zip_code_prefix,
    TRIM(seller_city) AS seller_city,
    TRIM(seller_state) AS seller_state
FROM olist_raw.olist_sellers_dataset;

ALTER TABLE olist_clean.sellers
    ADD PRIMARY KEY (seller_id);
CREATE INDEX idx_clean_sellers_state ON olist_clean.sellers (seller_state);

-- 4. Products (fix spelling + pre-join English category with fallback)
CREATE TABLE olist_clean.products AS
SELECT
    p.product_id,
    p.product_category_name,
    COALESCE(
        NULLIF(TRIM(t.product_category_name_english), ''),
        NULLIF(TRIM(p.product_category_name), ''),
        'uncategorized'
    ) AS category_en,
    p.product_name_lenght AS product_name_length,
    p.product_description_lenght AS product_description_length,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm
FROM olist_raw.olist_products_dataset p
LEFT JOIN olist_clean.category_translation t
    ON TRIM(p.product_category_name) = t.product_category_name;

ALTER TABLE olist_clean.products
    ADD PRIMARY KEY (product_id);
CREATE INDEX idx_clean_products_category_en ON olist_clean.products (category_en);

-- 5. Orders
CREATE TABLE olist_clean.orders AS
SELECT
    order_id,
    customer_id,
    TRIM(order_status) AS order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date
FROM olist_raw.olist_orders_dataset;

ALTER TABLE olist_clean.orders
    ADD PRIMARY KEY (order_id);
CREATE INDEX idx_clean_orders_purchase_ts ON olist_clean.orders (order_purchase_timestamp);
CREATE INDEX idx_clean_orders_status ON olist_clean.orders (order_status);
CREATE INDEX idx_clean_orders_customer ON olist_clean.orders (customer_id);

-- 6. Order Items
CREATE TABLE olist_clean.order_items AS
SELECT
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date,
    price,
    freight_value
FROM olist_raw.olist_order_items_dataset;

ALTER TABLE olist_clean.order_items
    ADD PRIMARY KEY (order_id, order_item_id);
CREATE INDEX idx_clean_order_items_product ON olist_clean.order_items (product_id);
CREATE INDEX idx_clean_order_items_seller ON olist_clean.order_items (seller_id);

-- 7. Payments
CREATE TABLE olist_clean.payments AS
SELECT
    order_id,
    payment_sequential,
    TRIM(payment_type) AS payment_type,
    payment_installments,
    payment_value
FROM olist_raw.olist_order_payments_dataset;

ALTER TABLE olist_clean.payments
    ADD PRIMARY KEY (order_id, payment_sequential);
CREATE INDEX idx_clean_payments_type ON olist_clean.payments (payment_type);

-- 8. Reviews: full copy + order-level deduplicated table (1 row per order_id)
CREATE TABLE olist_clean.order_reviews_all AS
SELECT
    review_id,
    order_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date,
    review_answer_timestamp
FROM olist_raw.olist_order_reviews_dataset;

CREATE INDEX idx_clean_reviews_all_order ON olist_clean.order_reviews_all (order_id);

CREATE TABLE olist_clean.reviews AS
SELECT DISTINCT ON (order_id)
    review_id,
    order_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date,
    review_answer_timestamp
FROM olist_raw.olist_order_reviews_dataset
ORDER BY order_id, review_creation_date DESC, review_answer_timestamp DESC NULLS LAST, review_id DESC;

ALTER TABLE olist_clean.reviews
    ADD PRIMARY KEY (order_id);
CREATE INDEX idx_clean_reviews_score ON olist_clean.reviews (review_score);

-- 9. Geolocation deduplicated by 5-digit zip prefix
CREATE TABLE olist_clean.geolocation_zip_prefix AS
SELECT
    geolocation_zip_code_prefix AS zip_code_prefix,
    AVG(geolocation_lat) AS avg_lat,
    AVG(geolocation_lng) AS avg_lng,
    MODE() WITHIN GROUP (ORDER BY TRIM(geolocation_city)) AS city,
    MODE() WITHIN GROUP (ORDER BY TRIM(geolocation_state)) AS state,
    COUNT(*) AS sample_points
FROM olist_raw.olist_geolocation_dataset
GROUP BY geolocation_zip_code_prefix;

ALTER TABLE olist_clean.geolocation_zip_prefix
    ADD PRIMARY KEY (zip_code_prefix);

-- Add rich comments on olist_clean tables for schema retrieval
COMMENT ON TABLE olist_clean.orders IS '核心清洗订单主表：一行一单(order_id)，含下单/支付/揽收/送达/预计送达时间与订单状态';
COMMENT ON TABLE olist_clean.order_items IS '核心订单商品明细表：一行一商品项(order_id, order_item_id)，含商品价(price)与运费(freight_value)';
COMMENT ON TABLE olist_clean.payments IS '核心订单支付流水表：一行一笔支付(order_id, payment_sequential)，含支付方式与实付金额(payment_value)';
COMMENT ON TABLE olist_clean.reviews IS '订单级去重评价表：按order_id取最新一条评价，含评分(review_score 1~5)';
COMMENT ON TABLE olist_clean.order_reviews_all IS '未去重原始评价全量明细表（仅用于审计核查，常规聚合请用reviews）';
COMMENT ON TABLE olist_clean.customers IS '买家映射表：含每单customer_id与唯一真实用户customer_unique_id及所在州customer_state';
COMMENT ON TABLE olist_clean.products IS '商品维表：含标准化英文品类category_en(空值已兜底为uncategorized)及商品尺寸重量';
COMMENT ON TABLE olist_clean.sellers IS '卖家维表：含卖家ID(seller_id)及发货州(seller_state)/城市';
COMMENT ON TABLE olist_clean.geolocation_zip_prefix IS '5位邮编前缀去重地理维表：聚合经纬度均值与州/城市众数';
COMMENT ON TABLE olist_clean.category_translation IS '葡语到英语商品品类翻译映射表';

ANALYZE olist_clean.orders;
ANALYZE olist_clean.order_items;
ANALYZE olist_clean.payments;
ANALYZE olist_clean.reviews;
ANALYZE olist_clean.customers;
ANALYZE olist_clean.products;
ANALYZE olist_clean.sellers;
ANALYZE olist_clean.geolocation_zip_prefix;
ANALYZE olist_clean.category_translation;
