# =============================================================================
# build_dimensions.py
# Orchestrator — Build All Gold Dimensions
# =============================================================================
#
# Chạy toàn bộ dim: python build_dimensions.py
# Hoặc Airflow DAG gọi từng run() riêng lẻ.
#
# Thứ tự load (dependency order):
#   dim_date       → không phụ thuộc ai
#   dim_product    → không phụ thuộc ai
#   dim_geography  → không phụ thuộc ai
#   dim_vendor     → không phụ thuộc ai
#   dim_customer   → SCD Type 2
#   dim_seller     → SCD Type 2
# =============================================================================

import os

from pyspark.sql import SparkSession

import build_dim_date
import build_dim_customer
import build_dim_product
import build_dim_geography
import build_dim_vendor
import build_dim_seller
from gold_utils import upsert_to_gold, read_silver


# =============================================================================
# SPARK INIT
# =============================================================================

def init_spark() -> SparkSession:
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("AdventureWorks - Build All Dimensions")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =============================================================================
# MAIN
# =============================================================================

def main():
    spark = init_spark()

    print("\n" + "=" * 70)
    print("  BUILD GOLD DIMENSIONS")
    print("=" * 70)

    # ── [1/6] dim_date ────────────────────────────────────────────────────── #
    # Chạy 1 lần — không cần chạy lại trừ khi muốn mở rộng phạm vi ngày
    print("\n[1/6] dim_date ...")
    dim_date = build_dim_date.build_dim_date(spark, "2010-01-01", "2030-12-31")
    upsert_to_gold(spark, dim_date, "dim_date", "date_key")
    print("  [✓] dim_date")

    # ── [2/6] dim_product — SCD Type 2 (track giá) ──────────────────────────── #
    print("\n[2/6] dim_product (SCD Type 2 — track standard_cost, list_price) ...")
    build_dim_product.run(spark)   # scd2_merge() bên trong
    print("  [✓] dim_product")

    # ── [3/6] dim_geography ───────────────────────────────────────────────── #
    print("\n[3/6] dim_geography ...")
    silver_geography = read_silver(spark, "geography")
    dim_geography = build_dim_geography.build_dim_geography(silver_geography)
    upsert_to_gold(spark, dim_geography, "dim_geography", "geography_key")
    print("  [✓] dim_geography")

    # ── [4/6] dim_vendor ──────────────────────────────────────────────────── #
    print("\n[4/6] dim_vendor ...")
    silver_vendor = read_silver(spark, "vendor")
    dim_vendor = build_dim_vendor.build_dim_vendor(silver_vendor)
    upsert_to_gold(spark, dim_vendor, "dim_vendor", "vendor_key")
    print("  [✓] dim_vendor")

    # ── [5/6] dim_customer — SCD Type 2 ──────────────────────────────────── #
    print("\n[5/6] dim_customer (SCD Type 2) ...")
    build_dim_customer.run(spark)   # scd2_merge() bên trong

    # ── [6/6] dim_seller — SCD Type 2 ────────────────────────────────────── #
    print("\n[6/6] dim_seller (SCD Type 2) ...")
    build_dim_seller.run(spark)     # scd2_merge() bên trong

    print("\n" + "=" * 70)
    print("  ALL DIMENSIONS BUILT SUCCESSFULLY")
    print("=" * 70)

    spark.stop()


if __name__ == "__main__":
    main()