# =============================================================================
# build_dim_seller.py
# Build Gold Dimension - Seller (SCD Type 2)
# =============================================================================
#
# Chạy độc lập:  python build_dim_seller.py
# Chạy từ orchestrator: import build_dim_seller; build_dim_seller.run(spark)
#
# SCD Type 2:
#   - Tracked columns : seller_name, commission_pct, sales_quota, bonus
#   - Surrogate key   : sha2(seller_id || effective_date, 256)
#   - Lần đầu        : INSERT tất cả với is_current=TRUE
#   - Lần sau        : EXPIRE bản cũ → INSERT bản mới nếu có thay đổi
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
# SPARK INIT (dùng khi chạy file standalone)
# =============================================================================

def init_spark() -> SparkSession:
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("Build Gold - Dim Seller (SCD2)")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =============================================================================
# TRANSFORM
# =============================================================================

def build_dim_seller(df, effective_date: str = None) -> "DataFrame":
    """
    Transform Silver seller → dim_seller với SCD Type 2 columns.

    Surrogate key = sha2(seller_id || effective_date, 256)
    → Mỗi phiên bản có key riêng, fact table giữ đúng seller_key tại thời điểm order.
    """
    eff_date = effective_date or str(date.today())

    df = df.fillna({
        "full_name":     "Unknown",
        "SalesQuota":    0,
        "Bonus":         0,
        "CommissionPct": 0,
        "SalesYTD":      0,
        "SalesLastYear": 0
    })

    return df.select(
        # Surrogate key (bao gồm ngày hiệu lực → unique per version)
        F.sha2(
            F.concat_ws("||", F.col("seller_id").cast("string"), F.lit(eff_date)),
            256
        ).alias("seller_key"),

        F.col("seller_id"),
        F.initcap(F.col("full_name")).alias("seller_name"),
        (F.col("CommissionPct") * 100).cast("decimal(5,2)").alias("commission_pct"),
        F.col("SalesQuota").cast("decimal(18,4)").alias("sales_quota"),
        F.col("Bonus").cast("decimal(18,4)").alias("bonus"),
        F.col("SalesYTD").cast("decimal(18,4)").alias("sales_ytd"),
        F.col("SalesLastYear").cast("decimal(18,4)").alias("sales_last_year"),

        # SCD Type 2 metadata
        F.lit(eff_date).cast("date").alias("effective_date"),
        F.lit(None).cast("date").alias("expiry_date"),
        F.lit(True).alias("is_current"),
        F.lit(1).cast("short").alias("version")
    )


def build_unknown_seller(spark: SparkSession) -> "DataFrame":
    """Tạo dòng Unknown Seller — surrogate key cố định = 'UNKNOWN'."""
    return spark.createDataFrame([{
        "seller_key":    UNKNOWN_KEY,
        "seller_id":     -1,
        "seller_name":   "Unknown / N/A",
        "commission_pct": 0.0,
        "sales_quota":   0.0,
        "bonus":         0.0,
        "sales_ytd":     0.0,
        "sales_last_year": 0.0,
        "effective_date": "2000-01-01",
        "expiry_date":   None,
        "is_current":    True,
        "version":       1
    }])


# =============================================================================
# ENTRY POINT (chạy standalone hoặc từ orchestrator)
# =============================================================================

def run(spark: SparkSession) -> int:
    """Được gọi từ build_dimensions.py hoặc Airflow DAG."""
    print("\n" + "=" * 60)
    print("  Building Gold Dimension : dim_seller  [SCD Type 2]")
    print("=" * 60)

    silver = read_silver(spark, "seller")
    dim    = build_dim_seller(silver)

    inserted = scd2_merge(
        spark        = spark,
        new_df       = dim,
        table_name   = "dim_seller",
        biz_key_col  = "seller_id",
        sk_col       = "seller_key",
        tracked_cols = ["seller_name", "commission_pct", "sales_quota", "bonus"]
    )

    print(f"  [✓] dim_seller → {inserted:,} row(s) upserted")
    return inserted


def main():
    spark = init_spark()
    run(spark)
    spark.stop()


if __name__ == "__main__":
    main()