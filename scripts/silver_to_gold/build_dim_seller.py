# =============================================================================
# build_dim_seller.py
# Build Gold Dimension - Seller
# =============================================================================

import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window


# =============================================================================
# SPARK
# =============================================================================

def init_spark():

    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("Build Gold - Dim Seller")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    return spark


# =============================================================================
# READ
# =============================================================================

def read_seller(spark):

    return spark.read.parquet(
        "s3a://silver/seller"
    )


# =============================================================================
# BUILD DIM SELLER
# =============================================================================

def build_dim_seller(df):

    window = Window.orderBy("seller_id")

    df = (
        df
        .withColumn(
            "seller_key",
            F.row_number().over(window)
        )
    )

    df = (
        df.fillna({
            "full_name": "Unknown",
            "SalesQuota": 0,
            "Bonus": 0,
            "CommissionPct": 0,
            "SalesYTD": 0,
            "SalesLastYear": 0
        })
    )

    df = (
        df.withColumn(
            "commission_pct",
            (F.col("CommissionPct") * 100).cast("decimal(5,2)")
        )
    )

    df = (
        df.withColumn(
            "created_at",
            F.current_timestamp()
        )
    )

    return (

        df.select(

            "seller_key",

            "seller_id",

            F.col("full_name").alias("seller_name"),

            F.col("SalesQuota").alias("sales_quota"),

            F.col("Bonus").alias("bonus"),

            "commission_pct",

            F.col("SalesYTD").alias("sales_ytd"),

            F.col("SalesLastYear").alias("sales_last_year"),

            "created_at"

        )

    )


# =============================================================================
# WRITE
# =============================================================================

def write_dim(df):

    (
        df.write
        .format("jdbc")
        .option(
            "url",
            "jdbc:postgresql://postgres_gold_dw:5432/gold_dw"
        )
        .option("dbtable", "dim_seller")
        .option("user", "gold_user")
        .option("password", "adminpassword")
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )


# =============================================================================
# MAIN
# =============================================================================

def main():

    spark = init_spark()

    print("=" * 60)
    print("Building Gold Dimension : dim_seller")
    print("=" * 60)

    seller = read_seller(spark)

    dim_seller = build_dim_seller(seller)

    write_dim(dim_seller)

    print(
        f"Total Sellers : {dim_seller.count()}"
    )

    spark.stop()

    print("[SUCCESS] gold/dim_seller")


if __name__ == "__main__":

    main()