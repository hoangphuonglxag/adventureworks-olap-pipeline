# =============================================================================
# build_fact_customer_behavior.py
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
        .appName("Build Gold - Fact Customer Behavior")
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

def build_fact_customer_behavior(
    header_df,
    detail_df,
    customer_dim
):

    #-------------------------------------------------------
    # Join Header + Detail
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
    # Lookup Customer Key
    #-------------------------------------------------------

    df = (

        df.join(

            customer_dim.select(
                "customer_key",
                "customer_id"
            ),

            "customer_id",

            "left"

        )

    )

    #-------------------------------------------------------
    # Customer Metrics
    #-------------------------------------------------------

    fact = (

        df.groupBy(

            "customer_key"

        )

        .agg(

            F.countDistinct(
                "order_id"
            ).alias("total_orders"),

            F.sum(
                "OrderQty"
            ).alias("total_quantity"),

            F.sum(
                "LineTotal"
            ).alias("total_amount"),

            F.avg(
                "LineTotal"
            ).alias("avg_order_value"),

            F.min(
                "OrderDate"
            ).alias("first_purchase"),

            F.max(
                "OrderDate"
            ).alias("last_purchase")

        )

    )

    #-------------------------------------------------------
    # Recency
    #-------------------------------------------------------

    fact = (

        fact.withColumn(

            "recency_days",

            F.datediff(

                F.current_date(),

                F.col("last_purchase")

            )

        )

    )

    #-------------------------------------------------------
    # Customer Segment (Simple RFM)
    #-------------------------------------------------------

    fact = (

        fact.withColumn(

            "customer_segment",

            F.when(
                (F.col("total_amount") >= 10000)
                &
                (F.col("total_orders") >= 10),
                "VIP"
            )

            .when(
                F.col("total_orders") >= 5,
                "Loyal"
            )

            .when(
                F.col("recency_days") > 365,
                "Lost"
            )

            .otherwise(
                "Regular"
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
        .option("dbtable", "fact_customer_behavior")
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

    customer = read_postgres_table(
        spark,
        "dim_customer"
    )

    fact = build_fact_customer_behavior(
        header,
        detail,
        customer
    )

    write_fact(fact)

    print(
        f"Customer Behavior Rows : {fact.count()}"
    )

    spark.stop()


if __name__ == "__main__":

    main()