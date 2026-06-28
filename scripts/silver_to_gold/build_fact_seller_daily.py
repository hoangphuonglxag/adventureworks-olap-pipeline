# =============================================================================
# build_fact_seller_daily.py
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
        .appName("Build Gold - Fact Seller Daily")
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

def build_fact_seller_daily(
    header_df,
    detail_df,
    seller_dim
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
    # Lookup Seller Key
    # --------------------------------------------------------

    df = (
        df.join(
            seller_dim.select(
                "seller_key",
                "seller_id",
                "commission_pct"
            ),
            df.sales_person_id == seller_dim.seller_id,
            "left"
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
    # Commission Earned
    # commission_pct trong dim_seller đang là %
    # ví dụ 5.00 nghĩa là 5%
    # --------------------------------------------------------

    df = (
        df.withColumn(
            "commission_earned",
            F.col("revenue")
            * (F.col("commission_pct") / 100)
        )
    )

    # --------------------------------------------------------
    # Aggregate
    # --------------------------------------------------------

    fact = (

        df.groupBy(

            "date_key",

            "seller_key"

        )

        .agg(

            F.countDistinct(
                "order_id"
            ).alias(
                "order_count"
            ),

            F.countDistinct(
                "customer_id"
            ).alias(
                "customer_count"
            ),

            F.sum(
                "OrderQty"
            ).alias(
                "quantity_sold"
            ),

            F.sum(
                "revenue"
            ).alias(
                "revenue"
            ),

            F.sum(
                "commission_earned"
            ).alias(
                "commission_earned"
            )

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
        .option("dbtable", "fact_seller_daily")
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

    seller = read_postgres_table(
        spark,
        "dim_seller"
    )

    fact = build_fact_seller_daily(
        header,
        detail,
        seller
    )

    write_fact(fact)

    print(
        f"Seller Daily Rows : {fact.count()}"
    )

    spark.stop()


if __name__ == "__main__":

    main()