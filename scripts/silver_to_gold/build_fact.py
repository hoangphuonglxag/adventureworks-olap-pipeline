# =============================================================================
# build_fact.py
# Orchestrator — Build All Gold Fact Tables  (Incremental + UPSERT)
# =============================================================================
#
# Chạy toàn bộ fact: python build_fact.py
# Hoặc Airflow DAG gọi từng run() riêng lẻ.
#
# Thứ tự load:
#   fact_order             → cần dim_customer, dim_product, dim_seller, dim_geography
#   fact_product_daily     → cần dim_product
#   fact_seller_daily      → cần dim_seller
#   fact_order_daily       → không cần dim (tự aggregate)
#   fact_inventory         → cần dim_product
#   fact_customer_behavior → cần dim_customer
#
# Tất cả đều dùng Incremental Load (watermark) + UPSERT (không DROP bảng Gold).
# =============================================================================

import os

from pyspark.sql import SparkSession

import build_fact_order
import build_fact_product_daily
import build_fact_seller_daily
import build_fact_order_daily
import build_fact_inventory
import build_fact_customer_behavior


# =============================================================================
# SPARK INIT
# =============================================================================

def init_spark() -> SparkSession:
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("AdventureWorks - Build All Facts")
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
    print("  BUILD GOLD FACT TABLES  [Incremental + UPSERT]")
    print("=" * 70)

    results = {}

    # ── [1/6] fact_order ─────────────────────────────────────────────────── #
    print("\n[1/6] fact_order ...")
    results["fact_order"] = build_fact_order.run(spark)

    # ── [2/6] fact_product_daily ──────────────────────────────────────────── #
    print("\n[2/6] fact_product_daily ...")
    results["fact_product_daily"] = build_fact_product_daily.run(spark)

    # ── [3/6] fact_seller_daily ───────────────────────────────────────────── #
    print("\n[3/6] fact_seller_daily ...")
    results["fact_seller_daily"] = build_fact_seller_daily.run(spark)

    # ── [4/6] fact_order_daily ────────────────────────────────────────────── #
    print("\n[4/6] fact_order_daily ...")
    results["fact_order_daily"] = build_fact_order_daily.run(spark)

    # ── [5/6] fact_inventory ─────────────────────────────────────────────── #
    print("\n[5/6] fact_inventory ...")
    results["fact_inventory"] = build_fact_inventory.run(spark)

    # ── [6/6] fact_customer_behavior ─────────────────────────────────────── #
    print("\n[6/6] fact_customer_behavior ...")
    results["fact_customer_behavior"] = build_fact_customer_behavior.run(spark)

    # ── Summary ───────────────────────────────────────────────────────────── #
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    for table, count in results.items():
        status = f"{count:,} rows upserted" if count > 0 else "SKIPPED (no new data)"
        print(f"  {table:<30} → {status}")
    print("=" * 70)

    spark.stop()


if __name__ == "__main__":
    main()