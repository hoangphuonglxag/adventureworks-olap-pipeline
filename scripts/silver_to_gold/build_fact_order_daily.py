# =============================================================================
# build_fact_order_daily.py
# =============================================================================

import os

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
        .appName("Build Gold - Fact Order Daily")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    return spark


# =============================================================================
# READ
# =============================================================================

def read_table(spark, path):

    return spark.read.parquet(path)


# =============================================================================
# BUILD FACT
# =============================================================================

def build_fact_order_daily(
    header_df,
    detail_df
):

    # --------------------------------------------------------
    # Header + Detail
    # --------------------------------------------------------

    df = (
        header_df.alias("h")
        .join(
            detail_df.alias("d"),
            "order_id",
            "inner"
        )
    )

    # --------------------------------------------------------
    # Date Key
    # --------------------------------------------------------

    df = (
        df.withColumn(
            "date_key",
            F.date_format(
                "OrderDate",
                "yyyyMMdd"
            ).cast("int")
        )
    )

    # --------------------------------------------------------
    # Revenue
    # --------------------------------------------------------

    df = (
        df.withColumn(
            "revenue",
            F.col("UnitPrice")
            * F.col("OrderQty")
            * (
                1 - F.col("UnitPriceDiscount")
            )
        )
    )

    # --------------------------------------------------------
    # Gross Profit
    # --------------------------------------------------------

    df = (
        df.withColumn(
            "gross_profit",
            (
                F.col("UnitPrice")
                -
                (
                    F.col("SubTotal")
                    / F.col("OrderQty")
                )
            )
            *
            F.col("OrderQty")
        )
    )

    # --------------------------------------------------------
    # Aggregate
    # --------------------------------------------------------

    fact = (

        df.groupBy(

            "date_key"

        )

        .agg(

            F.countDistinct(
                "order_id"
            ).alias(
                "daily_order_count"
            ),

            F.countDistinct(
                "customer_id"
            ).alias(
                "daily_customer_count"
            ),

            F.sum(
                "OrderQty"
            ).alias(
                "daily_quantity"
            ),

            F.sum(
                "revenue"
            ).alias(
                "daily_revenue"
            ),

            F.sum(
                "gross_profit"
            ).alias(
                "daily_gross_profit"
            ),

            F.avg(
                "revenue"
            ).alias(
                "average_order_value"
            )

        )

        .orderBy(
            "date_key"
        )

    )

    return fact


# =============================================================================
# WRITE
# =============================================================================

def write_fact(df):

    (
        df.write
        .format("jdbc")
        .option(
            "url",
            "jdbc:postgresql://postgres_gold_dw:5432/gold_dw"
        )
        .option("dbtable", "fact_order_daily")
        .option("user", "gold_user")
        .option("password", "adminpassword")
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )
#=============================================================================
# READ POSTGRES
#=============================================================================
def read_postgres_table(spark, table):

    return (
        spark.read
        .format("jdbc")
        .option(
            "url",
            "jdbc:postgresql://postgres_gold_dw:5432/gold_dw"
        )
        .option("dbtable", table)
        .option("user", "gold_user")
        .option("password", "adminpassword")
        .option("driver", "org.postgresql.Driver")
        .load()
    )

# =============================================================================
# MAIN
# =============================================================================

def main():

    spark = init_spark()

    header = read_table(
        spark,
        "s3a://silver/sales_order_header"
    )

    detail = read_table(
        spark,
        "s3a://silver/sales_order_detail"
    )

    fact = build_fact_order_daily(
        header,
        detail
    )

    write_fact(fact)

    print(
        f"Daily Records : {fact.count()}"
    )

    spark.stop()

    print("[SUCCESS] gold/fact_order_daily")


if __name__ == "__main__":

    main()