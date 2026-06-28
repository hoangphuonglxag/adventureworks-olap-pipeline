# =============================================================================
# build_fact_product_daily.py
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
        .appName("Build Gold - Fact Product Daily")
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

def build_fact_product_daily(
    header_df,
    detail_df,
    product_dim
):

    #-------------------------------------------------------
    # Header + Detail
    #-------------------------------------------------------

    df = (

        header_df.alias("h")

        .join(

            detail_df.alias("d"),

            "order_id",

            "inner"

        )

    )

    #-------------------------------------------------------
    # Product Key
    #-------------------------------------------------------

    df = (

        df.join(

            product_dim.select(

                "product_key",

                "product_id",

                "standard_cost"

            ),

            "product_id",

            "left"

        )

    )

    #-------------------------------------------------------
    # Date Key
    #-------------------------------------------------------

    df = (

        df.withColumn(

            "date_key",

            F.date_format(

                "OrderDate",

                "yyyyMMdd"

            ).cast("int")

        )

    )

    #-------------------------------------------------------
    # Gross Profit
    #-------------------------------------------------------

    df = (

        df.withColumn(

            "gross_profit",

            (

                F.col("UnitPrice")

                -

                F.col("standard_cost")

            )

            *

            F.col("OrderQty")

        )

    )

    #-------------------------------------------------------
    # Aggregate
    #-------------------------------------------------------

    fact = (

        df.groupBy(

            "date_key",

            "product_key"

        )

        .agg(

            F.sum(

                "OrderQty"

            ).alias(

                "quantity_sold"

            ),

            F.sum(

                "LineTotal"

            ).alias(

                "revenue"

            ),

            F.sum(

                "gross_profit"

            ).alias(

                "gross_profit"

            ),

            F.countDistinct(

                "order_id"

            ).alias(

                "order_count"

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
        .option("dbtable", "fact_product_daily")
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

    product = read_postgres_table(

        spark,

        "dim_product"

    )

    fact = build_fact_product_daily(

        header,

        detail,

        product

    )

    write_fact(

        fact

    )

    print(

        f"Product Daily Rows : {fact.count()}"

    )

    spark.stop()


if __name__ == "__main__":

    main()