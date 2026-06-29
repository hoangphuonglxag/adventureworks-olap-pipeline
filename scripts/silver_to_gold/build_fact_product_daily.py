# =============================================================================
# build_fact_product_daily.py
# Build Gold Fact - Product Daily  (Incremental Load + UPSERT)
# =============================================================================
#
# Grain: 1 dòng = 1 sản phẩm / 1 ngày
# Watermark key: "fact_product_daily"
#
# TEMPORAL JOIN với dim_product (SCD Type 2):
#   Tìm phiên bản dim_product có hiệu lực tại thời điểm order_date.
#   → standard_cost dùng để tính gross_profit luôn chính xác theo lịch sử.
#
#   Điều kiện join:
#     product_id match AND
#     order_date >= effective_date AND
#     (expiry_date IS NULL OR order_date < expiry_date)
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

WATERMARK_KEY = "fact_product_daily"


# =============================================================================
# SPARK INIT
# =============================================================================

def init_spark() -> SparkSession:
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("Build Gold - Fact Product Daily (Incremental)")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =============================================================================
# TRANSFORM
# =============================================================================

def build_fact_product_daily(header_df, detail_df, dim_product_all) -> "DataFrame":
    """
    Grain: 1 dòng = 1 sản phẩm / 1 ngày.

    dim_product_all: TẤT CẢ các phiên bản của dim_product (cả is_current=FALSE).
    Temporal join để lấy đúng standard_cost tại thời điểm order_date.

    Gross profit = (unit_price_of_order - standard_cost_at_that_time) * qty
    """
    df = header_df.alias("h").join(detail_df.alias("d"), "order_id", "inner")

    # ── TEMPORAL JOIN: tìm product version có hiệu lực tại order_date ─────── #
    # Điều kiện:
    #   1. product_id khớp
    #   2. order_date >= effective_date (version đã có hiệu lực)
    #   3. expiry_date IS NULL (đang active) HOẶC order_date < expiry_date (chưa expire)
    df = df.join(
        dim_product_all.alias("p"),
        (F.col("d.product_id") == F.col("p.product_id")) &
        (F.col("h.order_date") >= F.col("p.effective_date")) &
        (
            F.col("p.expiry_date").isNull() |
            (F.col("h.order_date") < F.col("p.expiry_date"))
        ),
        "left"
    )

    df = df.withColumn(
        "date_key",
        F.date_format(F.col("h.order_date"), "yyyyMMdd").cast("int")
    )

    # Gross profit dùng standard_cost tại thời điểm order (temporal join đã đảm bảo)
    df = df.withColumn(
        "gross_profit_per_unit",
        F.col("d.unit_price") - F.coalesce(F.col("p.standard_cost"), F.lit(0.0))
    )

    fact = (
        df.groupBy(
            "date_key",
            F.coalesce(F.col("p.product_key"), F.lit(UNKNOWN_KEY)).alias("product_key")
        )
        .agg(
            F.sum("d.order_qty").cast("int").alias("quantity_sold"),
            F.sum("d.line_total").cast("decimal(18,4)").alias("revenue"),
            F.sum(
                F.col("gross_profit_per_unit") * F.col("d.order_qty")
            ).cast("decimal(18,4)").alias("gross_profit"),
            F.countDistinct("d.order_id").cast("int").alias("order_count"),
            # Snapshot giá cuối ngày để tham khảo
            F.avg("p.standard_cost").cast("decimal(18,4)").alias("avg_standard_cost"),
            F.avg("p.list_price").cast("decimal(18,4)").alias("avg_list_price")
        )
    )

    return fact.withColumn(
        "fact_product_daily_key",
        F.sha2(F.concat_ws("||", F.col("date_key").cast("string"), F.col("product_key")), 256)
    ).select(
        "fact_product_daily_key", "date_key", "product_key",
        "quantity_sold", "revenue", "gross_profit", "order_count",
        "avg_standard_cost", "avg_list_price"
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

def run(spark: SparkSession) -> int:
    run_ts = datetime.now(tz=timezone.utc)

    print("\n" + "=" * 60)
    print("  Building Gold Fact : fact_product_daily  [Incremental]")
    print("  → Temporal join dim_product (SCD2 price history)")
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

    # Đọc TẤT CẢ phiên bản dim_product (kể cả expired) cho temporal join
    dim_product_all = read_pg_table(spark, "dim_product")

    fact     = build_fact_product_daily(header, detail, dim_product_all)
    upserted = upsert_to_gold(spark, fact, "fact_product_daily", "fact_product_daily_key")
    print(f"  [✓] fact_product_daily → {upserted:,} row(s) upserted")

    update_watermark(spark, WATERMARK_KEY, run_ts, inc_count)
    return upserted


def main():
    spark = init_spark()
    run(spark)
    spark.stop()


if __name__ == "__main__":
    main()