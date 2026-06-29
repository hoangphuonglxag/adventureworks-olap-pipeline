# =============================================================================
# silver_to_gold.py
# Silver (MinIO Parquet) --> Gold (PostgreSQL Star Schema) ETL
# Cơ chế: UPSERT (INSERT ON CONFLICT DO UPDATE) — không DROP bảng
# AdventureWorks2022
# =============================================================================

import os
import time
from pyspark.sql import SparkSession

import gold_builders as GB

# Biến lưu trữ báo cáo tiến độ tầng Gold
GOLD_REPORT = []

# =============================================================================
# CONFIGURATION & SPARK INIT
# =============================================================================

POSTGRES_URL      = os.environ.get("POSTGRES_GOLD_URL",      "jdbc:postgresql://postgres_gold_dw:5432/gold_dw")
POSTGRES_USER     = os.environ.get("POSTGRES_GOLD_USER",     "gold_user")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_GOLD_PASSWORD", "adminpassword")
POSTGRES_DRIVER   = "org.postgresql.Driver"


def init_spark() -> SparkSession:
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("AdventureWorks Silver To Gold Star Schema")
        .getOrCreate()
    )

    # Set S3A config trực tiếp vào Hadoop Configuration object
    # (cách đáng tin cậy nhất — bypass spark.hadoop.* prefix translation)
    hc = spark.sparkContext._jsc.hadoopConfiguration()
    hc.set("fs.s3a.endpoint",          "http://minio:9000")
    hc.set("fs.s3a.access.key",        access_key)
    hc.set("fs.s3a.secret.key",        secret_key)
    hc.set("fs.s3a.path.style.access", "true")
    hc.set("fs.s3a.impl",              "org.apache.hadoop.fs.s3a.S3AFileSystem")

    spark.sparkContext.setLogLevel("ERROR")
    return spark


# =============================================================================
# UTILITIES: READ SILVER / EXECUTE SQL / UPSERT TO GOLD
# =============================================================================

def read_silver(spark: SparkSession, table: str):
    """Đọc dữ liệu sạch từ tầng Silver trên MinIO S3"""
    return spark.read.parquet(f"s3a://silver/{table}")


def execute_sql(spark: SparkSession, sql: str):
    """
    Thực thi DML/DDL trực tiếp trên PostgreSQL qua Py4J JDBC.
    Không cần psycopg2 — dùng Java DriverManager có sẵn trong JVM của Spark.
    """
    conn = None
    try:
        conn = spark._jvm.java.sql.DriverManager.getConnection(
            POSTGRES_URL, POSTGRES_USER, POSTGRES_PASSWORD
        )
        conn.setAutoCommit(True)
        stmt = conn.createStatement()
        stmt.execute(sql)
    finally:
        if conn:
            conn.close()


def write_gold_upsert(spark: SparkSession, df, table_name: str, pk_col: str, model_type: str):
    """
    UPSERT dữ liệu vào bảng Gold PostgreSQL theo 3 bước:
      1. Ghi df vào bảng staging (overwrite) — nhanh, Spark lo
      2. INSERT INTO <target> SELECT * FROM <staging> ON CONFLICT (pk) DO UPDATE SET ...
      3. DROP TABLE <staging>

    Ưu điểm:
    - Bảng Gold không bao giờ bị xóa ->> Dashboard luôn có data
    - Chạy lại pipeline không bị duplicate
    - Dim table giữ nguyên surrogate key mapping
    """
    start_time  = time.time()
    count       = df.count()
    staging     = f"{table_name}_stg"

    # BƯỚC 1 — Ghi vào bảng staging (tạm, overwrite toàn bộ)
    (
        df.write
        .format("jdbc")
        .option("url",      POSTGRES_URL)
        .option("dbtable",  staging)
        .option("user",     POSTGRES_USER)
        .option("password", POSTGRES_PASSWORD)
        .option("driver",   POSTGRES_DRIVER)
        .mode("overwrite")
        .save()
    )

    # BƯỚC 2 — Build và thực thi câu UPSERT
    cols     = df.columns
    non_pk   = [c for c in cols if c != pk_col]
    col_list = ", ".join([f'"{c}"' for c in cols])
    update_set = ", ".join([f'"{c}" = EXCLUDED."{c}"' for c in non_pk])

    upsert_sql = f"""
        INSERT INTO {table_name} ({col_list})
        SELECT {col_list} FROM {staging}
        ON CONFLICT ("{pk_col}") DO UPDATE SET {update_set};
    """
    execute_sql(spark, upsert_sql)

    # BƯỚC 3 — Dọn staging
    execute_sql(spark, f"DROP TABLE IF EXISTS {staging};")

    duration = round(time.time() - start_time, 2)
    GOLD_REPORT.append({
        "Type":     model_type,
        "Table":    table_name.upper(),
        "Rows":     count,
        "Duration": duration
    })


# =============================================================================
# PRINT DASHBOARD REPORT
# =============================================================================

def print_gold_dashboard():
    print("\n" + "="*80)
    print(f"{'ADVENTUREWORKS GOLD LAYER (POSTGRESQL STAR SCHEMA) REPORT':^80}")
    print("="*80)
    print(f"| {'Type':<6} | {'Postgres Table Name':<30} | {'Rows Upserted':<15} | {'Duration (s)':<10} |")
    print("-"*80)
    for row in GOLD_REPORT:
        print(f"| {row['Type']:<6} | {row['Table']:<30} | {row['Rows']:<15,} | {row['Duration']:<10} |")
    print("="*80)


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def main():
    spark = init_spark()
    print("\n>>> Gold Pipeline Activated. UPSERT mode → PostgreSQL Star Schema...")

    # -------------------------------------------------------------------------
    # 1. ĐỌC TỪNG BẢNG SILVER
    # -------------------------------------------------------------------------
    print("[1/2] Reading Silver tables from MinIO...")
    silver_customer  = read_silver(spark, "customer")
    silver_product   = read_silver(spark, "product")
    silver_geography = read_silver(spark, "geography")
    silver_seller    = read_silver(spark, "seller")
    silver_header    = read_silver(spark, "sales_order_header")
    silver_detail    = read_silver(spark, "sales_order_detail")

    # -------------------------------------------------------------------------
    # 2. BUILD + UPSERT DIMENSIONS
    # -------------------------------------------------------------------------
    print("[2/2] Building models and upserting to Postgres...")

    dim_date = GB.build_dim_date(spark)
    write_gold_upsert(spark, dim_date, "dim_date", "date_key", "DIM")
    print("  [✓] dim_date")

    dim_customer = GB.build_dim_customer(silver_customer)
    write_gold_upsert(spark, dim_customer, "dim_customer", "customer_key", "DIM")
    print("  [✓] dim_customer")

    dim_product = GB.build_dim_product(silver_product)
    write_gold_upsert(spark, dim_product, "dim_product", "product_key", "DIM")
    print("  [✓] dim_product")

    dim_geography = GB.build_dim_geography(silver_geography)
    write_gold_upsert(spark, dim_geography, "dim_geolocation", "geography_key", "DIM")
    print("  [✓] dim_geolocation")

    dim_seller = GB.build_dim_seller(silver_seller)
    write_gold_upsert(spark, dim_seller, "dim_seller", "seller_key", "DIM")
    print("  [✓] dim_seller")

    # -------------------------------------------------------------------------
    # 3. BUILD + UPSERT FACTS
    # -------------------------------------------------------------------------

    fact_order = GB.build_fact_order(silver_header, dim_customer, dim_seller)
    write_gold_upsert(spark, fact_order, "fact_order", "order_fact_key", "FACT")
    print("  [✓] fact_order")

    fact_product_daily = GB.build_fact_product_daily(silver_header, silver_detail, dim_product)
    write_gold_upsert(spark, fact_product_daily, "fact_product_daily", "product_fact_key", "FACT")
    print("  [✓] fact_product_daily")

    fact_order_daily = GB.build_fact_order_daily(fact_product_daily)
    write_gold_upsert(spark, fact_order_daily, "fact_order_daily", "order_daily_key", "FACT")
    print("  [✓] fact_order_daily")

    # -------------------------------------------------------------------------
    # 4. REPORT
    # -------------------------------------------------------------------------
    print_gold_dashboard()
    spark.stop()


if __name__ == "__main__":
    main()