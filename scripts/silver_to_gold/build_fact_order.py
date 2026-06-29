# =============================================================================
# build_fact_order.py
# Build Gold Fact - Order  (Incremental Load + UPSERT)
# =============================================================================
#
# TEMPORAL JOIN với dim_product (SCD Type 2):
#   Fact lưu product_key của phiên bản giá có hiệu lực tại thời điểm order.
#   → Khi join Dashboard sau này vẫn biết được giá nào đang áp dụng.
#
# Chạy độc lập  : python build_fact_order.py
# Chạy từ build_fact.py: import build_fact_order; build_fact_order.run(spark)
#
# Incremental Load:
#   - Watermark key : "fact_order"
#   - Filter column : order_date >= last watermark
#   - Lần đầu      : load toàn bộ (watermark = 2000-01-01)
#   - Lần sau       : chỉ load đơn hàng mới hơn mốc trước
#
# UPSERT: staging table → INSERT ON CONFLICT DO UPDATE (không DROP bảng Gold)
# =============================================================================

import os
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from gold_utils import (
    read_silver,
    read_pg_table,
    upsert_to_gold,
    get_watermark,
    get_watermark_date_str,
    update_watermark,
    UNKNOWN_KEY
)

WATERMARK_KEY = "fact_order"


# =============================================================================
# SPARK INIT
# =============================================================================

def init_spark() -> SparkSession:
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("Build Gold - Fact Order (Incremental)")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =============================================================================
# TRANSFORM
# =============================================================================

def build_fact_order(header_df, detail_df, dim_customer, dim_product,
                     dim_geography, dim_seller, dim_date) -> "DataFrame":
    """
    Grain: 1 dòng = 1 dòng chi tiết đơn hàng.

    Join dim_seller dùng is_current=TRUE (đọc từ ngoài vào) để lấy đúng
    seller_key hiện tại tại thời điểm chạy pipeline.
    Nếu không match → fallback về UNKNOWN_KEY (Online orders không có SalesPersonID).
    """
    df = header_df.alias("h").join(detail_df.alias("d"), "order_id", "inner")

    df = df.join(
        dim_customer.select("customer_key", "customer_id"), "customer_id", "left"
    )
    # TEMPORAL JOIN dim_product: lấy product_key của phiên bản giá active tại order_date
    df = df.join(
        dim_product.alias("p"),
        (F.col("d.product_id") == F.col("p.product_id")) &
        (F.col("h.order_date") >= F.col("p.effective_date")) &
        (
            F.col("p.expiry_date").isNull() |
            (F.col("h.order_date") < F.col("p.expiry_date"))
        ),
        "left"
    )

    df = df.join(
        dim_seller.select("seller_key", "seller_id"),
        df.sales_person_id == dim_seller.seller_id,
        "left"
    )

    df = df.withColumn(
        "date_key",
        F.date_format(F.col("order_date"), "yyyyMMdd").cast("int")
    )

    if "address_id" in header_df.columns:
        df = df.join(
            dim_geography.select("geography_key", "address_id"), "address_id", "left"
        )
    else:
        df = df.withColumn("geography_key", F.lit(None).cast("string"))

    return df.select(
        # Surrogate key của fact = sha2 của order_detail_id
        F.sha2(F.col("d.order_detail_id").cast("string"), 256).alias("fact_order_key"),
        F.col("h.order_id"),
        "date_key",
        F.coalesce(F.col("customer_key"), F.lit(UNKNOWN_KEY)).alias("customer_key"),
        F.coalesce(F.col("product_key"),  F.lit(UNKNOWN_KEY)).alias("product_key"),
        F.coalesce(F.col("seller_key"),   F.lit(UNKNOWN_KEY)).alias("seller_key"),
        "geography_key",
        F.col("h.sales_channel"),
        F.col("d.order_qty").cast("int"),
        F.col("d.unit_price").cast("decimal(18,4)"),
        F.col("d.unit_price_discount").cast("decimal(10,4)"),
        F.col("d.line_total").cast("decimal(18,4)"),
        F.col("h.sub_total").cast("decimal(18,4)"),
        F.col("h.tax_amt").cast("decimal(18,4)"),
        F.col("h.freight_amt").cast("decimal(18,4)"),
        F.col("h.total_due").cast("decimal(18,4)")
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

def run(spark: SparkSession) -> int:
    """Được gọi từ build_fact.py hoặc Airflow DAG."""
    run_ts = datetime.now(tz=timezone.utc)

    print("\n" + "=" * 60)
    print("  Building Gold Fact : fact_order  [Incremental + UPSERT]")
    print("=" * 60)

    # -- Watermark incremental ------------------------------------------------
    wm_date = get_watermark_date_str(spark, WATERMARK_KEY)
    print(f"  [WATERMARK] Lọc order_date >= {wm_date}")

    header_all = read_silver(spark, "sales_order_header")
    detail_all = read_silver(spark, "sales_order_detail")

    header = header_all.filter(F.col("order_date") >= F.lit(wm_date).cast("date"))
    detail = detail_all.join(header.select("order_id"), "order_id", "inner")

    inc_count = header.count()
    if inc_count == 0:
        print("  [SKIP] Không có đơn hàng mới — bỏ qua.")
        return 0

    print(f"  [INCREMENTAL] {inc_count:,} order(s) mới")

    # -- Đọc dim (chỉ lấy is_current=TRUE cho seller & customer) -------------
    dim_customer = read_pg_table(
        spark, "(SELECT customer_id, customer_key FROM dim_customer WHERE is_current=TRUE) t"
    )
    # TẤT CẢ phiên bản dim_product (kể cả expired) để temporal join
    dim_product  = read_pg_table(spark, "dim_product")
    dim_geography= read_pg_table(spark, "dim_geography")
    dim_seller   = read_pg_table(
        spark, "(SELECT seller_id, seller_key FROM dim_seller WHERE is_current=TRUE) t"
    )
    dim_date     = read_pg_table(spark, "dim_date")

    # -- Build fact -----------------------------------------------------------
    fact = build_fact_order(
        header, detail, dim_customer, dim_product, dim_geography, dim_seller, dim_date
    )

    # -- UPSERT ---------------------------------------------------------------
    upserted = upsert_to_gold(spark, fact, "fact_order", "fact_order_key")
    print(f"  [✓] fact_order → {upserted:,} row(s) upserted")

    # -- Cập nhật watermark ---------------------------------------------------
    update_watermark(spark, WATERMARK_KEY, run_ts, inc_count)

    return upserted


def main():
    spark = init_spark()
    run(spark)
    spark.stop()


if __name__ == "__main__":
    main()