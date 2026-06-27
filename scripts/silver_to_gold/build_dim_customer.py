# =============================================================================
# build_dim_customer.py
# Build Gold Dimension - Customer
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
        .appName("Build Gold - Dim Customer")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    return spark


# =============================================================================
# READ
# =============================================================================

def read_customer(spark):

    return spark.read.parquet(
        "s3a://silver/customer"
    )


# =============================================================================
# BUILD DIM CUSTOMER
# =============================================================================

def build_dim_customer(df):

    # Sinh Surrogate Key
    window = Window.orderBy("customer_id")

    df = (
        df
        .withColumn(
            "customer_key",
            F.row_number().over(window)
        )
    )

    # Chuẩn hóa tên
    df = (
        df
        .withColumn(
            "customer_name",
            F.initcap(F.col("customer_name"))
        )
    )

    # Thay NULL
    df = (
        df
        .fillna({
            "customer_name": "Unknown",
            "customer_type": "Unknown",
            "account_number": "N/A"
        })
    )

    return (
        df.select(

            "customer_key",

            "customer_id",

            "customer_name",

            "customer_type",

            "account_number"

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
        .option("dbtable", "dim_customer")
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
    print("Building Gold Dimension : dim_customer")
    print("=" * 60)

    customer = read_customer(spark)

    dim_customer = build_dim_customer(customer)

    write_dim(dim_customer)

    print(
        f"Total Customers : {dim_customer.count()}"
    )

    spark.stop()

    print("[SUCCESS] gold/dim_customer")


if __name__ == "__main__":

    main()