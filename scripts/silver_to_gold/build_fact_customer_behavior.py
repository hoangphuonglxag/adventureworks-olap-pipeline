# =============================================================================
# build_fact_customer_behavior.py
# Build Gold Fact - Customer Behavior  (Incremental + UPSERT)
# =============================================================================
#
# Chạy độc lập  : python build_fact_customer_behavior.py
# Chạy từ build_fact.py: import build_fact_customer_behavior; build_fact_customer_behavior.run(spark)
#
# Grain: 1 dòng = 1 khách hàng (lifetime aggregate)
# Watermark key: "fact_customer_behavior"
#
# NOTE: Bảng này là lifetime aggregate nên mỗi lần incremental load vẫn cần
#       tính lại toàn bộ cho các customer có đơn hàng mới trong kỳ.
#       Dùng UPSERT để update record cũ của customer đó.
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

WATERMARK_KEY = "fact_customer_behavior"


# =============================================================================
# SPARK INIT
# =============================================================================

def init_spark() -> SparkSession:
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("Build Gold - Fact Customer Behavior (Incremental)")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =============================================================================
# TRANSFORM
# =============================================================================

def build_fact_customer_behavior(header_df, detail_df, dim_customer) -> "DataFrame":
    """
    Grain: 1 dòng = 1 khách hàng.
    Metrics: total_orders, total_quantity, total_amount, avg_order_value,
             first_purchase, last_purchase, recency_days, customer_segment (RFM đơn giản).

    dim_customer phải đã filter is_current=TRUE (truyền từ ngoài vào).
    """
    df = (
        header_df.alias("h")
        .join(detail_df.alias("d"), "order_id", "inner")
        .join(
            dim_customer.select("customer_key", "customer_id"),
            "customer_id", "left"
        )
    )

    fact = (
        df.groupBy(
            F.coalesce(F.col("customer_key"), F.lit(UNKNOWN_KEY)).alias("customer_key")
        )
        .agg(
            F.countDistinct("order_id").cast("int").alias("total_orders"),
            F.sum("order_qty").cast("int").alias("total_quantity"),
            F.sum("line_total").cast("decimal(18,4)").alias("total_amount"),
            F.avg("line_total").cast("decimal(18,4)").alias("avg_order_value"),
            F.min("order_date").alias("first_purchase"),
            F.max("order_date").alias("last_purchase")
        )
    )

    fact = fact.withColumn(
        "recency_days",
        F.datediff(F.current_date(), F.col("last_purchase")).cast("int")
    )

    # Simple RFM segmentation
    fact = fact.withColumn(
        "customer_segment",
        F.when(
            (F.col("total_amount") >= 10000) & (F.col("total_orders") >= 10), "VIP"
        ).when(
            F.col("total_orders") >= 5, "Loyal"
        ).when(
            F.col("recency_days") > 365, "Lost"
        ).otherwise("Regular")
    )

    # Surrogate key = sha2(customer_key) — 1 dòng / 1 customer
    return fact.withColumn(
        "fact_customer_behavior_key",
        F.sha2(F.col("customer_key"), 256)
    ).select(
        "fact_customer_behavior_key",
        "customer_key",
        "total_orders",
        "total_quantity",
        "total_amount",
        "avg_order_value",
        "first_purchase",
        "last_purchase",
        "recency_days",
        "customer_segment"
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

def run(spark: SparkSession) -> int:
    """Được gọi từ build_fact.py hoặc Airflow DAG."""
    run_ts = datetime.now(tz=timezone.utc)

    print("\n" + "=" * 60)
    print("  Building Gold Fact : fact_customer_behavior  [Incremental]")
    print("=" * 60)

    wm_date = get_watermark_date_str(spark, WATERMARK_KEY)
    print(f"  [WATERMARK] Lọc order_date >= {wm_date}")

    header_all = read_silver(spark, "sales_order_header")
    detail_all = read_silver(spark, "sales_order_detail")

    # Lọc header theo watermark để xác định customer nào cần update
    header_new = header_all.filter(F.col("order_date") >= F.lit(wm_date).cast("date"))
    inc_count  = header_new.count()

    if inc_count == 0:
        print("  [SKIP] Không có dữ liệu mới — bỏ qua.")
        return 0

    print(f"  [INCREMENTAL] {inc_count:,} order(s) mới")

    # Lấy danh sách customer_id có đơn mới → chỉ tính lại lifetime cho những customer đó
    new_customer_ids = header_new.select("customer_id").distinct()
    header_affected  = header_all.join(new_customer_ids, "customer_id", "inner")
    detail_affected  = detail_all.join(header_affected.select("order_id"), "order_id", "inner")

    # Đọc dim_customer chỉ lấy is_current=TRUE
    dim_customer = read_pg_table(
        spark,
        "(SELECT customer_id, customer_key FROM dim_customer WHERE is_current=TRUE) t"
    )

    fact     = build_fact_customer_behavior(header_affected, detail_affected, dim_customer)
    upserted = upsert_to_gold(spark, fact, "fact_customer_behavior", "fact_customer_behavior_key")
    print(f"  [✓] fact_customer_behavior → {upserted:,} row(s) upserted")

    update_watermark(spark, WATERMARK_KEY, run_ts, inc_count)
    return upserted


def main():
    spark = init_spark()
    run(spark)
    spark.stop()


if __name__ == "__main__":
    main()