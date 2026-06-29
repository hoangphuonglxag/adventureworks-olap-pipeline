-- =============================================================================
-- create_gold_tables.sql
-- DDL: Khởi tạo Star Schema cho tầng Gold (PostgreSQL)
-- Database: adventureworks_dw
--
-- Chạy 1 lần khi khởi tạo database.
-- Sau đó pipeline dùng UPSERT (ON CONFLICT DO UPDATE) để load data.
--
-- v2 Changes:
--   + SCD Type 2 columns cho dim_seller, dim_customer
--   + pipeline_watermark table (Incremental Load tracking)
--   + UNKNOWN member rows cho dim_seller, dim_customer (thay cho -1)
--   + Tách surrogate key dùng SHA2 thay vì row_number()
-- =============================================================================


-- ============================================================
-- DIMENSION TABLES
-- ============================================================

-- dim_date: generated table, không thay đổi — UPSERT thông thường
CREATE TABLE IF NOT EXISTS dim_date (
    date_key    INTEGER     PRIMARY KEY,
    full_date   DATE        NOT NULL,
    day         SMALLINT,
    day_name    VARCHAR(10),
    day_of_week SMALLINT,
    week        SMALLINT,
    month       SMALLINT,
    month_name  VARCHAR(15),
    quarter     SMALLINT,
    year        SMALLINT,
    is_weekend  BOOLEAN
);

-- dim_product: SCD Type 2
-- Tracked: standard_cost, list_price
-- Surrogate key = sha2(product_id || effective_date, 256)
-- → product_id có thể xuất hiện nhiều lần (mỗi lần giá đổi = 1 phiên bản mới)
CREATE TABLE IF NOT EXISTS dim_product (
    product_key      VARCHAR(64) PRIMARY KEY,
    product_id       INTEGER,           -- Business key (NOT UNIQUE vì có nhiều version)
    product_name     VARCHAR(200),
    product_number   VARCHAR(50),
    color            VARCHAR(30),
    size             VARCHAR(20),
    standard_cost    DECIMAL(18,4),     -- ← tracked
    list_price       DECIMAL(18,4),     -- ← tracked
    category_name    VARCHAR(100),
    subcategory_name VARCHAR(100),
    -- SCD Type 2 metadata
    effective_date   DATE         NOT NULL DEFAULT CURRENT_DATE,
    expiry_date      DATE,
    is_current       BOOLEAN      NOT NULL DEFAULT TRUE,
    version          SMALLINT     NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_dim_product_id         ON dim_product(product_id);
CREATE INDEX IF NOT EXISTS idx_dim_product_is_current ON dim_product(is_current);
-- Index hỗ trợ temporal join: tìm phiên bản active tại order_date
CREATE INDEX IF NOT EXISTS idx_dim_product_dates      ON dim_product(product_id, effective_date, expiry_date);

-- dim_geography: SCD Type 1 — UPSERT thông thường
CREATE TABLE IF NOT EXISTS dim_geography (
    geography_key       VARCHAR(64) PRIMARY KEY,
    address_id          INTEGER     UNIQUE,
    address_line1       VARCHAR(255),
    address_line2       VARCHAR(255),
    city                VARCHAR(100),
    state_name          VARCHAR(100),
    country_name        VARCHAR(100),
    territory_name      VARCHAR(100),
    territory_group     VARCHAR(50),
    postal_code         VARCHAR(20),
    created_at          TIMESTAMP
);

-- dim_vendor: SCD Type 1 — UPSERT thông thường
CREATE TABLE IF NOT EXISTS dim_vendor (
    vendor_key             VARCHAR(64) PRIMARY KEY,
    vendor_id              INTEGER     UNIQUE,
    account_number         VARCHAR(50),
    vendor_name            VARCHAR(200),
    credit_rating          SMALLINT,
    preferred_vendor       VARCHAR(50),
    vendor_status          VARCHAR(50),
    created_at             TIMESTAMP
);

-- ----------------------------------------------------------------
-- dim_customer — SCD Type 2
-- Tracked: customer_name, customer_type
-- Surrogate key = sha2(customer_id || effective_date, 256)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key    VARCHAR(64)  PRIMARY KEY,
    customer_id     INTEGER,
    customer_name   VARCHAR(200),
    customer_type   VARCHAR(20),
    account_number  VARCHAR(50),
    -- SCD2 metadata
    effective_date  DATE         NOT NULL DEFAULT CURRENT_DATE,
    expiry_date     DATE,
    is_current      BOOLEAN      NOT NULL DEFAULT TRUE,
    version         SMALLINT     NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_dim_customer_id         ON dim_customer(customer_id);
CREATE INDEX IF NOT EXISTS idx_dim_customer_is_current ON dim_customer(is_current);

-- ----------------------------------------------------------------
-- dim_seller — SCD Type 2
-- Tracked: seller_name, commission_pct, sales_quota, bonus
-- Surrogate key = sha2(seller_id || effective_date, 256)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_seller (
    seller_key      VARCHAR(64)  PRIMARY KEY,
    seller_id       INTEGER,
    seller_name     VARCHAR(200),
    commission_pct  DECIMAL(5,2),
    sales_quota     DECIMAL(18,4),
    bonus           DECIMAL(18,4),
    sales_ytd       DECIMAL(18,4),
    sales_last_year DECIMAL(18,4),
    -- SCD2 metadata
    effective_date  DATE         NOT NULL DEFAULT CURRENT_DATE,
    expiry_date     DATE,
    is_current      BOOLEAN      NOT NULL DEFAULT TRUE,
    version         SMALLINT     NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_dim_seller_id         ON dim_seller(seller_id);
CREATE INDEX IF NOT EXISTS idx_dim_seller_is_current ON dim_seller(is_current);


-- ============================================================
-- FACT TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS fact_order (
    fact_order_key      VARCHAR(64)  PRIMARY KEY,
    order_id            INTEGER,
    date_key            INTEGER,
    customer_key        VARCHAR(64),
    product_key         VARCHAR(64),
    seller_key          VARCHAR(64),
    geography_key       VARCHAR(64),
    sales_channel       VARCHAR(20),
    order_qty           INTEGER,
    unit_price          DECIMAL(18,4),
    unit_price_discount DECIMAL(10,4),
    line_total          DECIMAL(18,4),
    sub_total           DECIMAL(18,4),
    tax_amt             DECIMAL(18,4),
    freight_amt         DECIMAL(18,4),
    total_due           DECIMAL(18,4)
);

CREATE TABLE IF NOT EXISTS fact_product_daily (
    fact_product_daily_key VARCHAR(64) PRIMARY KEY,
    date_key               INTEGER,
    product_key            VARCHAR(64),   -- SCD2 key: trỏ đúng phiên bản giá tại thời điểm order
    quantity_sold          INTEGER,
    revenue                DECIMAL(18,4),
    gross_profit           DECIMAL(18,4),
    order_count            INTEGER,
    avg_standard_cost      DECIMAL(18,4), -- Snapshot giá vốn tại thời điểm bán
    avg_list_price         DECIMAL(18,4)  -- Snapshot giá niêm yết tại thời điểm bán
);

CREATE TABLE IF NOT EXISTS fact_seller_daily (
    fact_seller_daily_key VARCHAR(64) PRIMARY KEY,
    date_key              INTEGER,
    seller_key            VARCHAR(64),
    order_count           INTEGER,
    customer_count        INTEGER,
    quantity_sold         INTEGER,
    revenue               DECIMAL(18,4),
    commission_earned     DECIMAL(18,4)
);

CREATE TABLE IF NOT EXISTS fact_order_daily (
    fact_order_daily_key  VARCHAR(64) PRIMARY KEY,
    date_key              INTEGER,
    daily_order_count     INTEGER,
    daily_customer_count  INTEGER,
    daily_quantity        INTEGER,
    daily_revenue         DECIMAL(18,4),
    average_order_value   DECIMAL(18,4)
);

CREATE TABLE IF NOT EXISTS fact_inventory (
    fact_inventory_key VARCHAR(64) PRIMARY KEY,
    product_key        VARCHAR(64),
    location_id        INTEGER,
    quantity           INTEGER,
    shelf              VARCHAR(20),
    bin                SMALLINT
);

CREATE TABLE IF NOT EXISTS fact_customer_behavior (
    fact_customer_behavior_key VARCHAR(64) PRIMARY KEY,
    customer_key               VARCHAR(64),
    total_orders               INTEGER,
    total_quantity             INTEGER,
    total_amount               DECIMAL(18,4),
    avg_order_value            DECIMAL(18,4),
    first_purchase             DATE,
    last_purchase              DATE,
    recency_days               INTEGER,
    customer_segment           VARCHAR(20)
);


-- ============================================================
-- WATERMARK TABLE — Incremental Load Tracking
-- ============================================================
-- Convention tên:
--   "fact_order"          → watermark cho Silver→Gold fact_order
--   "fact_product_daily"  → watermark cho fact_product_daily
--   etc.
-- ============================================================

CREATE TABLE IF NOT EXISTS pipeline_watermark (
    table_name  VARCHAR(100) PRIMARY KEY,
    last_loaded TIMESTAMP    NOT NULL,
    row_count   INTEGER      DEFAULT 0,
    updated_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- UNKNOWN MEMBER ROWS
-- ============================================================
-- Thay thế cho giá trị -1 khi dimension lookup không tìm thấy.
-- Ví dụ: Online orders không có SalesPersonID → seller_key = 'UNKNOWN'
-- ============================================================

INSERT INTO dim_seller (
    seller_key, seller_id, seller_name,
    commission_pct, sales_quota, bonus, sales_ytd, sales_last_year,
    effective_date, expiry_date, is_current, version
) VALUES (
    'UNKNOWN', -1, 'Unknown / N/A',
    0, 0, 0, 0, 0,
    '2000-01-01', NULL, TRUE, 1
) ON CONFLICT (seller_key) DO NOTHING;

INSERT INTO dim_customer (
    customer_key, customer_id, customer_name, customer_type, account_number,
    effective_date, expiry_date, is_current, version
) VALUES (
    'UNKNOWN', -1, 'Unknown / N/A', 'Unknown', 'N/A',
    '2000-01-01', NULL, TRUE, 1
) ON CONFLICT (customer_key) DO NOTHING;


-- ============================================================
-- INDEXES — Tối ưu query Dashboard
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_fact_order_date     ON fact_order(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_order_customer ON fact_order(customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_order_seller   ON fact_order(seller_key);
CREATE INDEX IF NOT EXISTS idx_fact_order_product  ON fact_order(product_key);

CREATE INDEX IF NOT EXISTS idx_fact_pd_date        ON fact_product_daily(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_pd_product     ON fact_product_daily(product_key);

CREATE INDEX IF NOT EXISTS idx_fact_sd_date        ON fact_seller_daily(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_sd_seller      ON fact_seller_daily(seller_key);

CREATE INDEX IF NOT EXISTS idx_fact_od_date        ON fact_order_daily(date_key);


-- ============================================================
-- MIGRATION: Thêm SCD2 cols vào bảng đã tồn tại trước đó
-- (Safe to run multiple times — ADD COLUMN IF NOT EXISTS)
-- ============================================================

ALTER TABLE dim_seller   ADD COLUMN IF NOT EXISTS effective_date DATE    DEFAULT CURRENT_DATE;
ALTER TABLE dim_seller   ADD COLUMN IF NOT EXISTS expiry_date    DATE;
ALTER TABLE dim_seller   ADD COLUMN IF NOT EXISTS is_current     BOOLEAN DEFAULT TRUE;
ALTER TABLE dim_seller   ADD COLUMN IF NOT EXISTS version        SMALLINT DEFAULT 1;

ALTER TABLE dim_customer ADD COLUMN IF NOT EXISTS effective_date DATE    DEFAULT CURRENT_DATE;
ALTER TABLE dim_customer ADD COLUMN IF NOT EXISTS expiry_date    DATE;
ALTER TABLE dim_customer ADD COLUMN IF NOT EXISTS is_current     BOOLEAN DEFAULT TRUE;
ALTER TABLE dim_customer ADD COLUMN IF NOT EXISTS version        SMALLINT DEFAULT 1;

-- dim_product: thêm SCD2 cols + bỏ UNIQUE constraint cũ (nếu có) 
ALTER TABLE dim_product  ADD COLUMN IF NOT EXISTS effective_date DATE    DEFAULT CURRENT_DATE;
ALTER TABLE dim_product  ADD COLUMN IF NOT EXISTS expiry_date    DATE;
ALTER TABLE dim_product  ADD COLUMN IF NOT EXISTS is_current     BOOLEAN DEFAULT TRUE;
ALTER TABLE dim_product  ADD COLUMN IF NOT EXISTS version        SMALLINT DEFAULT 1;

-- fact_product_daily: thêm cột snapshot giá
ALTER TABLE fact_product_daily ADD COLUMN IF NOT EXISTS avg_standard_cost DECIMAL(18,4);
ALTER TABLE fact_product_daily ADD COLUMN IF NOT EXISTS avg_list_price    DECIMAL(18,4);
