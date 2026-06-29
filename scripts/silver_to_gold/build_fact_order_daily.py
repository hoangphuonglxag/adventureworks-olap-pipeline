# =============================================================================
# build_fact_order_daily.py
# Build Gold Fact - Order Daily  (Incremental Load + UPSERT)
# =============================================================================
#
# Grain: 1 dòng = 1 ngày (aggregate toàn bộ orders trong ngày)
# Watermark key: "fact_order_daily"
# =============================================================================

import os
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from gold_utils import (
    read_silver,
    upsert_to_gold,
    get_watermark_date_str,
    update_watermark
)

WATERMARK_KEY = "fact_order_daily"


# =============================================================================
# SPARK INIT
# =============================================================================

def init_spark() -> SparkSession:
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("Build Gold - Fact Order Daily (Incremental)")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =============================================================================
# TRANSFORM
# =============================================================================

def build_fact_order_daily(header_df, detail_df) -> "DataFrame":
    """
    Grain: 1 dòng = 1 ngày.
    Aggregate: order_count, customer_count, quantity, revenue, gross_profit, avg_order_value.
    """
    df = header_df.alias("h").join(detail_df.alias("d"), "order_id", "inner")

    df = df.withColumn(
        "date_key",
        F.date_format(F.col("order_date"), "yyyyMMdd").cast("int")
    )

    df = df.withColumn(
        "revenue",
        F.col("unit_price") * F.col("order_qty") * (1 - F.coalesce(F.col("unit_price_discount"), F.lit(0.0)))
    )

    fact = (
        df.groupBy("date_key")
        .agg(
            F.countDistinct("order_id").cast("int").alias("daily_order_count"),
            F.countDistinct("customer_id").cast("int").alias("daily_customer_count"),
            F.sum("order_qty").cast("int").alias("daily_quantity"),
            F.sum("revenue").cast("decimal(18,4)").alias("daily_revenue"),
            F.avg("revenue").cast("decimal(18,4)").alias("average_order_value")
        )
        .orderBy("date_key")
    )

    return fact.withColumn(
        "fact_order_daily_key",
        F.sha2(F.col("date_key").cast("string"), 256)
    ).select(
        "fact_order_daily_key", "date_key",
        "daily_order_count", "daily_customer_count",
        "daily_quantity", "daily_revenue", "average_order_value"
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

def run(spark: SparkSession) -> int:
    run_ts = datetime.now(tz=timezone.utc)

    print("\n" + "=" * 60)
    print("  Building Gold Fact : fact_order_daily  [Incremental]")
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

    fact = build_fact_order_daily(header, detail)
    upserted = upsert_to_gold(spark, fact, "fact_order_daily", "fact_order_daily_key")
    print(f"  [✓] fact_order_daily → {upserted:,} row(s) upserted")

    update_watermark(spark, WATERMARK_KEY, run_ts, inc_count)
    return upserted


def main():
    spark = init_spark()
    run(spark)
    spark.stop()


if __name__ == "__main__":
    main()