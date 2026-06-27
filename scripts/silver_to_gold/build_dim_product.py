# =============================================================================
# build_dim_product.py
# Build Gold Dimension - Product
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
        .appName("Build Gold - Dim Product")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    return spark


# =============================================================================
# READ
# =============================================================================

def read_product(spark):

    return spark.read.parquet(
        "s3a://silver/product"
    )


# =============================================================================
# BUILD DIM PRODUCT
# =============================================================================

def build_dim_product(df):

    window = Window.orderBy("product_id")

    df = (
        df
        .withColumn(
            "product_key",
            F.row_number().over(window)
        )
    )

    df = (
        df
        .fillna({
            "product_name": "Unknown",
            "ProductNumber": "N/A",
            "Color": "Unknown",
            "Size": "Unknown",
            "category_name": "Unknown",
            "subcategory_name": "Unknown"
        })
    )

    df = (
        df
        .withColumn(
            "created_at",
            F.current_timestamp()
        )
    )

    return (

        df.select(

            "product_key",

            "product_id",

            "product_name",

            F.col("ProductNumber").alias("product_number"),

            F.col("Color").alias("color"),

            F.col("Size").alias("size"),

            F.col("StandardCost").alias("standard_cost"),

            F.col("ListPrice").alias("list_price"),

            "category_name",

            "subcategory_name",

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
        .option("dbtable", "dim_product")
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
    print("Building Gold Dimension : dim_product")
    print("=" * 60)

    product = read_product(spark)

    dim_product = build_dim_product(product)

    write_dim(dim_product)

    print(
        f"Total Products : {dim_product.count()}"
    )

    spark.stop()

    print("[SUCCESS] gold/dim_product")


if __name__ == "__main__":

    main()