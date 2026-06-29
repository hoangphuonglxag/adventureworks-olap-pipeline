# =============================================================================
# build_fact_seller_daily.py
# Build Gold Fact - Seller Daily  (Incremental Load + UPSERT)
# =============================================================================
#
# Grain: 1 dòng = 1 seller / 1 ngày
# Watermark key: "fact_seller_daily"
#
# NOTE: Online orders (sales_person_id=NULL) sẽ được gom vào seller_key='UNKNOWN'
# =============================================================================

import os
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from gold_utils import (
    read_silver,
    read_pg_table,
    upsert_to_gold,
    get_watermark_date_str,
    update_watermark,
    UNKNOWN_KEY
)

WATERMARK_KEY = "fact_seller_daily"


# =============================================================================
# SPARK INIT
# =============================================================================

def init_spark() -> SparkSession:
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("Build Gold - Fact Seller Daily (Incremental)")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =============================================================================
# TRANSFORM
# =============================================================================

def build_fact_seller_daily(header_df, detail_df, dim_seller) -> "DataFrame":
    """
    Grain: 1 dòng = 1 seller / 1 ngày.
    dim_seller phải đã filter is_current=TRUE (truyền từ ngoài vào).
    """
    df = header_df.alias("h").join(detail_df.alias("d"), "order_id", "inner")

    df = df.join(
        dim_seller.select("seller_key", "seller_id", "commission_pct"),
        df.sales_person_id == dim_seller.seller_id,
        "left"
    )

    df = df.withColumn(
        "date_key",
        F.date_format(F.col("order_date"), "yyyyMMdd").cast("int")
    )

    df = df.withColumn(
        "revenue",
        F.col("unit_price") * F.col("order_qty") * (1 - F.coalesce(F.col("unit_price_discount"), F.lit(0.0)))
    )

    df = df.withColumn(
        "commission_earned",
        F.col("revenue") * (F.coalesce(F.col("commission_pct"), F.lit(0.0)) / 100)
    )

    fact = (
        df.groupBy(
            "date_key",
            F.coalesce(F.col("seller_key"), F.lit(UNKNOWN_KEY)).alias("seller_key")
        )
        .agg(
            F.countDistinct("order_id").cast("int").alias("order_count"),
            F.countDistinct("customer_id").cast("int").alias("customer_count"),
            F.sum("order_qty").cast("int").alias("quantity_sold"),
            F.sum("revenue").cast("decimal(18,4)").alias("revenue"),
            F.sum("commission_earned").cast("decimal(18,4)").alias("commission_earned")
        )
    )

    return fact.withColumn(
        "fact_seller_daily_key",
        F.sha2(F.concat_ws("||", F.col("date_key").cast("string"), F.col("seller_key")), 256)
    ).select(
        "fact_seller_daily_key", "date_key", "seller_key",
        "order_count", "customer_count", "quantity_sold",
        "revenue", "commission_earned"
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

def run(spark: SparkSession) -> int:
    run_ts = datetime.now(tz=timezone.utc)

    print("\n" + "=" * 60)
    print("  Building Gold Fact : fact_seller_daily  [Incremental]")
    print("=" * 60)

    wm_date = get_watermark_date_str(spark, WATERMARK_KEY)
    print(f"  [WATERMARK] Lọc order_date >= {wm_date}")

    header_all = read_silver(spark, "sales_order_header")
    detail_all = read_silver(spark, "sales_order_detail")

    header = header_all.filter(F.col("order_date") >= F.lit(wm_date).cast("date"))
    detail = detail_all.join(header.select("order_id"), "order_id", "inner")

    inc_count = header.count()
    if inc_count == 0:
        print("  [SKIP] Không có dữ liệu mới — bỏ qua.")
        return 0

    print(f"  [INCREMENTAL] {inc_count:,} order(s)")

    dim_seller = read_pg_table(
        spark, "(SELECT seller_id, seller_key, commission_pct FROM dim_seller WHERE is_current=TRUE) t"
    )

    fact = build_fact_seller_daily(header, detail, dim_seller)
    upserted = upsert_to_gold(spark, fact, "fact_seller_daily", "fact_seller_daily_key")
    print(f"  [✓] fact_seller_daily → {upserted:,} row(s) upserted")

    update_watermark(spark, WATERMARK_KEY, run_ts, inc_count)
    return upserted


def main():
    spark = init_spark()
    run(spark)
    spark.stop()


if __name__ == "__main__":
    main()