# =============================================================================
# build_fact_inventory.py
# Build Gold Fact - Inventory  (Full Refresh + UPSERT)
# =============================================================================
#
# Chạy độc lập  : python build_fact_inventory.py
# Chạy từ build_fact.py: import build_fact_inventory; build_fact_inventory.run(spark)
#
# NOTE: Inventory là snapshot hiện tại (không có timestamp) → Full Refresh mỗi lần.
#       Dùng UPSERT thay vì overwrite để Dashboard không bị downtime.
# =============================================================================

import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from gold_utils import (
    read_silver,
    read_pg_table,
    upsert_to_gold,
    UNKNOWN_KEY
)


# =============================================================================
# SPARK INIT
# =============================================================================

def init_spark() -> SparkSession:
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("Build Gold - Fact Inventory (Full Refresh)")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =============================================================================
# TRANSFORM
# =============================================================================

def build_fact_inventory(inventory_df, dim_product) -> "DataFrame":
    """
    Grain: 1 dòng = 1 sản phẩm / 1 vị trí kho (product_id + location_id).
    Full Refresh mỗi lần vì inventory là snapshot không có timestamp.
    """
    fact = (
        inventory_df.alias("i")
        .join(
            dim_product.select("product_key", "product_id"),
            "product_id",
            "left"
        )
        .select(
            # Surrogate key = sha2(product_id || location_id)
            F.sha2(
                F.concat_ws("||",
                    F.col("product_id").cast("string"),
                    F.col("location_id").cast("string")),
                256
            ).alias("fact_inventory_key"),
            F.coalesce(F.col("product_key"), F.lit(UNKNOWN_KEY)).alias("product_key"),
            F.col("location_id"),
            F.col("shelf"),
            F.col("bin"),
            F.col("quantity").cast("int").alias("quantity")
        )
    )
    return fact


# =============================================================================
# ENTRY POINT
# =============================================================================

def run(spark: SparkSession) -> int:
    """Được gọi từ build_fact.py hoặc Airflow DAG."""
    print("\n" + "=" * 60)
    print("  Building Gold Fact : fact_inventory  [Full Refresh + UPSERT]")
    print("=" * 60)

    inventory  = read_silver(spark, "product_inventory")
    dim_product = read_pg_table(spark, "dim_product")

    fact     = build_fact_inventory(inventory, dim_product)
    upserted = upsert_to_gold(spark, fact, "fact_inventory", "fact_inventory_key")
    print(f"  [✓] fact_inventory → {upserted:,} row(s) upserted")
    return upserted


def main():
    spark = init_spark()
    run(spark)
    spark.stop()


if __name__ == "__main__":
    main()