# =============================================================================
# build_dim_geography.py
# Build Gold Dimension - Geography
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
        .appName("Build Gold - Dim Geography")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    return spark


# =============================================================================
# READ
# =============================================================================

def read_geography(spark):

    return spark.read.parquet(
        "s3a://silver/geography"
    )


# =============================================================================
# BUILD DIM GEOGRAPHY
# =============================================================================

def build_dim_geography(df):

    window = Window.orderBy("address_id")

    df = (
        df
        .withColumn(
            "geography_key",
            F.row_number().over(window)
        )
    )

    df = (
        df.fillna({
            "AddressLine1": "Unknown",
            "AddressLine2": "",
            "City": "Unknown",
            "state_name": "Unknown",
            "country_name": "Unknown",
            "territory_name": "Unknown",
            "territory_group": "Unknown",
            "PostalCode": "Unknown"
        })
    )

    df = (
        df.withColumn(
            "created_at",
            F.current_timestamp()
        )
    )

    return (

        df.select(

            "geography_key",

            "address_id",

            F.col("AddressLine1").alias("address_line1"),

            F.col("AddressLine2").alias("address_line2"),

            F.col("City").alias("city"),

            "state_name",

            "country_name",

            "territory_name",

            "territory_group",

            F.col("PostalCode").alias("postal_code"),

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
        .option("dbtable", "dim_geography")
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
    print("Building Gold Dimension : dim_geography")
    print("=" * 60)

    geography = read_geography(spark)

    dim_geography = build_dim_geography(
        geography
    )

    write_dim(
        dim_geography
    )

    print(
        f"Total Geography : {dim_geography.count()}"
    )

    spark.stop()

    print("[SUCCESS] gold/dim_geography")


if __name__ == "__main__":

    main()