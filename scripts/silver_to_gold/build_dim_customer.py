# =============================================================================
# build_dim_customer.py
# Build Gold Dimension - Customer (SCD Type 2)
# =============================================================================
#
# Chạy độc lập:  python build_dim_customer.py
# Chạy từ orchestrator: import build_dim_customer; build_dim_customer.run(spark)
#
# SCD Type 2:
#   - Tracked columns : customer_name, customer_type
#   - Surrogate key   : sha2(customer_id || effective_date, 256)
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
        .appName("Build Gold - Dim Customer (SCD2)")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =============================================================================
# TRANSFORM
# =============================================================================

def build_dim_customer(df, effective_date: str = None) -> "DataFrame":
    """
    Transform Silver customer → dim_customer với SCD Type 2 columns.

    Surrogate key = sha2(customer_id || effective_date, 256)
    """
    eff_date = effective_date or str(date.today())

    df = df.fillna({
        "customer_name":  "Unknown",
        "customer_type":  "Unknown",
        "account_number": "N/A"
    })

    return df.select(
        # Surrogate key
        F.sha2(
            F.concat_ws("||", F.col("customer_id").cast("string"), F.lit(eff_date)),
            256
        ).alias("customer_key"),

        F.col("customer_id"),
        F.initcap("customer_name").alias("customer_name"),
        F.col("customer_type"),
        F.col("account_number"),

        # SCD Type 2 metadata
        F.lit(eff_date).cast("date").alias("effective_date"),
        F.lit(None).cast("date").alias("expiry_date"),
        F.lit(True).alias("is_current"),
        F.lit(1).cast("short").alias("version")
    )


def build_unknown_customer(spark: SparkSession) -> "DataFrame":
    """Tạo dòng Unknown Customer — surrogate key cố định = 'UNKNOWN'."""
    return spark.createDataFrame([{
        "customer_key":   UNKNOWN_KEY,
        "customer_id":    -1,
        "customer_name":  "Unknown / N/A",
        "customer_type":  "Unknown",
        "account_number": "N/A",
        "effective_date": "2000-01-01",
        "expiry_date":    None,
        "is_current":     True,
        "version":        1
    }])


# =============================================================================
# ENTRY POINT
# =============================================================================

def run(spark: SparkSession) -> int:
    """Được gọi từ build_dimensions.py hoặc Airflow DAG."""
    print("\n" + "=" * 60)
    print("  Building Gold Dimension : dim_customer  [SCD Type 2]")
    print("=" * 60)

    silver = read_silver(spark, "customer")
    dim    = build_dim_customer(silver)

    inserted = scd2_merge(
        spark        = spark,
        new_df       = dim,
        table_name   = "dim_customer",
        biz_key_col  = "customer_id",
        sk_col       = "customer_key",
        tracked_cols = ["customer_name", "customer_type"]
    )

    print(f"  [✓] dim_customer → {inserted:,} row(s) upserted")
    return inserted


def main():
    spark = init_spark()
    run(spark)
    spark.stop()


if __name__ == "__main__":
    main()