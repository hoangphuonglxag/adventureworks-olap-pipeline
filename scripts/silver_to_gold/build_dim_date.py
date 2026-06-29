# =============================================================================
# build_dim_date.py
# Build Gold Dimension - Date
# =============================================================================

import os
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


# =============================================================================
# SPARK
# =============================================================================

def init_spark():

    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("Build Gold - Dim Date")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    return spark


# =============================================================================
# BUILD DIM DATE
# =============================================================================

def build_dim_date(spark, start_date, end_date):

    # Sinh danh sách ngày
    df = (
        spark.sql(
            f"""
            SELECT explode(
                sequence(
                    to_date('{start_date}'),
                    to_date('{end_date}'),
                    interval 1 day
                )
            ) AS full_date
            """
        )
    )

    df = (
        df
        .withColumn(
            "date_key",
            F.date_format("full_date", "yyyyMMdd").cast("int")
        )
        .withColumn(
            "day",
            F.dayofmonth("full_date")
        )
        .withColumn(
            "day_name",
            F.date_format("full_date", "EEEE")
        )
        .withColumn(
            "day_of_week",
            F.dayofweek("full_date")
        )
        .withColumn(
            "week",
            F.weekofyear("full_date")
        )
        .withColumn(
            "month",
            F.month("full_date")
        )
        .withColumn(
            "month_name",
            F.date_format("full_date", "MMMM")
        )
        .withColumn(
            "quarter",
            F.quarter("full_date")
        )
        .withColumn(
            "year",
            F.year("full_date")
        )
        .withColumn(
            "is_weekend",
            F.when(
                F.dayofweek("full_date").isin([1, 7]),
                True
            ).otherwise(False)
        )
    )

    return df.select(
        "date_key",
        "full_date",
        "day",
        "day_name",
        "day_of_week",
        "week",
        "month",
        "month_name",
        "quarter",
        "year",
        "is_weekend"
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
        .option("dbtable", "dim_date")
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
    print("Building Gold Dimension : dim_date")
    print("=" * 60)

    df = build_dim_date(
        spark,
        start_date="2010-01-01",
        end_date="2030-12-31"
    )

    write_dim(df)

    print(f"Total Records : {df.count()}")

    spark.stop()

    print("[SUCCESS] gold/dim_date")


if __name__ == "__main__":
    main()