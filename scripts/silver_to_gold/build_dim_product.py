# =============================================================================
# build_dim_product.py
# Build Gold Dimension - Product  (SCD Type 2)
# =============================================================================
#
# Chạy độc lập  : python build_dim_product.py
# Chạy từ orchestrator: import build_dim_product; build_dim_product.run(spark)
#
# SCD Type 2:
#   - Tracked columns : standard_cost, list_price
#     (Giá thay đổi → expire bản cũ, insert bản mới với key mới)
#   - Non-tracked     : product_name, color, size, category... (SCD1 behavior)
#   - Surrogate key   : sha2(product_id || effective_date, 256)
#
# TẠI SAO track standard_cost & list_price?
#   fact_product_daily tính gross_profit = (unit_price - standard_cost) × qty
#   Nếu overwrite standard_cost → gross_profit lịch sử bị SAI.
#   SCD2 cho phép fact temporal join đúng phiên bản giá tại thời điểm order.
# =============================================================================

import os
from datetime import date

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from gold_utils import (
    read_silver,
    scd2_merge,
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
        .appName("Build Gold - Dim Product (SCD2)")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =============================================================================
# TRANSFORM
# =============================================================================

def build_dim_product(df, effective_date: str = None) -> "DataFrame":
    """
    Transform Silver product → dim_product với SCD Type 2 columns.

    Surrogate key = sha2(product_id || effective_date, 256)
    → Mỗi lần giá thay đổi, product_key mới được tạo ra.
    → fact_product_daily temporal join để lấy đúng key tại thời điểm order.
    """
    eff_date = effective_date or "2010-01-01"

    df = df.fillna({
        "product_name":    "Unknown",
        "ProductNumber":   "N/A",
        "Color":           "Unknown",
        "Size":            "Unknown",
        "category_name":   "Unknown",
        "subcategory_name": "Unknown",
        "StandardCost":    0.0,
        "ListPrice":       0.0
    })

    return df.select(
        # Surrogate key (bao gồm ngày hiệu lực → unique per version)
        F.sha2(
            F.concat_ws("||", F.col("product_id").cast("string"), F.lit(eff_date)),
            256
        ).alias("product_key"),

        F.col("product_id"),
        F.col("product_name"),
        F.col("ProductNumber").alias("product_number"),
        F.col("Color").alias("color"),
        F.col("Size").alias("size"),
        F.col("StandardCost").cast("decimal(18,4)").alias("standard_cost"),
        F.col("ListPrice").cast("decimal(18,4)").alias("list_price"),
        F.col("category_name"),
        F.col("subcategory_name"),

        # SCD Type 2 metadata
        F.lit(eff_date).cast("date").alias("effective_date"),
        F.lit(None).cast("date").alias("expiry_date"),
        F.lit(True).alias("is_current"),
        F.lit(1).cast("short").alias("version")
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

def run(spark: SparkSession) -> int:
    """Được gọi từ build_dimensions.py hoặc Airflow DAG."""
    print("\n" + "=" * 60)
    print("  Building Gold Dimension : dim_product  [SCD Type 2]")
    print("  Tracked: standard_cost, list_price")
    print("=" * 60)

    silver = read_silver(spark, "product")
    dim    = build_dim_product(silver)

    inserted = scd2_merge(
        spark        = spark,
        new_df       = dim,
        table_name   = "dim_product",
        biz_key_col  = "product_id",
        sk_col       = "product_key",
        tracked_cols = ["standard_cost", "list_price"]   # Chỉ track giá
    )

    print(f"  [✓] dim_product → {inserted:,} row(s) upserted")
    return inserted


def main():
    spark = init_spark()
    run(spark)
    spark.stop()


if __name__ == "__main__":
    main()