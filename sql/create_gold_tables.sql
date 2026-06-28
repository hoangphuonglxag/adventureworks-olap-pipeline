-- =============================================================================
-- create_gold_tables.sql
-- DDL: Khởi tạo Star Schema cho tầng Gold (Chỉ chạy 1 lần đầu tiên)
-- Database: adventureworks_dw (PostgreSQL)
--
-- TẠI SAO CẦN FILE NÀY?
-- Pipeline Silver to Gold dùng cơ chế UPSERT (INSERT ON CONFLICT DO UPDATE).
-- UPSERT yêu cầu bảng TARGET phải tồn tại trước với PRIMARY KEY constraint.
-- Spark JDBC overwrite chỉ tạo bảng STAGING tạm, không tạo bảng Gold thật.
-- =============================================================================

-- ============================================================
-- DIMENSION TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INTEGER PRIMARY KEY,
    full_date    DATE           NOT NULL,
    day_name     VARCHAR(10),
    day_of_week  SMALLINT,
    month_num    SMALLINT,
    month_name   VARCHAR(15),
    quarter      SMALLINT,
    year         SMALLINT,
    is_weekend   BOOLEAN
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key  VARCHAR(64) PRIMARY KEY,
    customer_id   INTEGER,
    customer_type VARCHAR(20),
    full_name     VARCHAR(150),
    email         VARCHAR(100),
    phone         VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_key      VARCHAR(64) PRIMARY KEY,
    product_id       INTEGER,
    product_name     VARCHAR(200),
    product_number   VARCHAR(50),
    color            VARCHAR(30),
    size             VARCHAR(20),
    standard_cost    DECIMAL(18,4),
    list_price       DECIMAL(18,4),
    category_name    VARCHAR(100),
    subcategory_name VARCHAR(100),
    abc_class        CHAR(1)
);

CREATE TABLE IF NOT EXISTS dim_geolocation (
    geography_key       VARCHAR(64) PRIMARY KEY,
    address_id          INTEGER,
    city                VARCHAR(100),
    state_province_name VARCHAR(100),
    country_region_name VARCHAR(100),
    territory_name      VARCHAR(100),
    territory_group     VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS dim_seller (
    seller_key         VARCHAR(64) PRIMARY KEY,
    business_entity_id INTEGER,
    full_name          VARCHAR(150),
    commission_pct     DECIMAL(10,4),
    sales_quota        DECIMAL(18,4),
    bonus              DECIMAL(18,4)
);

-- ============================================================
-- FACT TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS fact_order (
    order_fact_key VARCHAR(64) PRIMARY KEY,
    order_id       INTEGER,
    date_key       INTEGER,
    customer_key   VARCHAR(64),
    seller_key     VARCHAR(64),
    territory_id   INTEGER,
    sales_channel  VARCHAR(20),
    total_due      DECIMAL(18,4),
    tax_amt        DECIMAL(18,4),
    freight_amt    DECIMAL(18,4),
    order_status   SMALLINT
);

CREATE TABLE IF NOT EXISTS fact_product_daily (
    product_fact_key VARCHAR(64) PRIMARY KEY,
    date_key         INTEGER,
    product_key      VARCHAR(64),
    territory_id     INTEGER,
    sales_channel    VARCHAR(20),
    quantity_sold    INTEGER,
    total_orders     INTEGER,
    revenue          DECIMAL(18,4),
    gross_profit     DECIMAL(18,4),
    avg_price        DECIMAL(18,4),
    return_qty       INTEGER,
    return_rate      DECIMAL(5,4)
);

CREATE TABLE IF NOT EXISTS fact_order_daily (
    order_daily_key   VARCHAR(64) PRIMARY KEY,
    date_key          INTEGER,
    territory_id      INTEGER,
    sales_channel     VARCHAR(20),
    daily_revenue     DECIMAL(18,4),
    daily_profit      DECIMAL(18,4),
    daily_order_count INTEGER
);

-- ============================================================
-- INDEXES (Tối ưu query Dashboard)
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_fact_order_date     ON fact_order(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_order_customer ON fact_order(customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_order_seller   ON fact_order(seller_key);

CREATE INDEX IF NOT EXISTS idx_fact_pd_date        ON fact_product_daily(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_pd_product     ON fact_product_daily(product_key);
CREATE INDEX IF NOT EXISTS idx_fact_pd_territory   ON fact_product_daily(territory_id);

CREATE INDEX IF NOT EXISTS idx_fact_od_date        ON fact_order_daily(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_od_territory   ON fact_order_daily(territory_id);
