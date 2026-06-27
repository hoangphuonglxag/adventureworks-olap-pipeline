# =============================================================================
# build_dim_vendor.py
# Build Gold Dimension - Vendor
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
        .appName("Build Gold - Dim Vendor")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    return spark


# =============================================================================
# READ
# =============================================================================

def read_vendor(spark):

    return spark.read.parquet(
        "s3a://silver/vendor"
    )


# =============================================================================
# BUILD DIM VENDOR
# =============================================================================

def build_dim_vendor(df):

    window = Window.orderBy("vendor_id")

    df = (
        df
        .withColumn(
            "vendor_key",
            F.row_number().over(window)
        )
    )

    df = (
        df.fillna({
            "AccountNumber": "N/A",
            "Name": "Unknown",
            "CreditRating": 0,
            "PreferredVendorStatus": False,
            "ActiveFlag": False
        })
    )

    df = (
        df.withColumn(
            "vendor_status",
            F.when(
                F.col("ActiveFlag") == True,
                "Active"
            ).otherwise("Inactive")
        )
    )

    df = (
        df.withColumn(
            "preferred_vendor",
            F.when(
                F.col("PreferredVendorStatus") == True,
                "Yes"
            ).otherwise("No")
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

            "vendor_key",

            "vendor_id",

            F.col("Name").alias("vendor_name"),

            F.col("AccountNumber").alias("account_number"),

            F.col("CreditRating").alias("credit_rating"),

            "preferred_vendor",

            "vendor_status",

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
        .option("dbtable", "dim_vendor")
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
    print("Building Gold Dimension : dim_vendor")
    print("=" * 60)

    vendor = read_vendor(spark)

    dim_vendor = build_dim_vendor(vendor)

    write_dim(dim_vendor)

    print(
        f"Total Vendors : {dim_vendor.count()}"
    )

    spark.stop()

    print("[SUCCESS] gold/dim_vendor")


if __name__ == "__main__":

    main()