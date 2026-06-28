# =============================================================================
# build_fact.py
# Build All Gold Facts
# =============================================================================

import os

from pyspark.sql import SparkSession

from build_fact_order import build_fact_order
from build_fact_inventory import build_fact_inventory
from build_fact_customer_behavior import build_fact_customer_behavior
from build_fact_product_daily import build_fact_product_daily
from build_fact_seller_daily import build_fact_seller_daily
from build_fact_order_daily import build_fact_order_daily


# =============================================================================
# SPARK
# =============================================================================

def init_spark():

    access_key = os.environ.get(
        "MINIO_ACCESS_KEY",
        "admin"
    )

    secret_key = os.environ.get(
        "MINIO_SECRET_KEY",
        "adminpassword"
    )

    spark = (
        SparkSession.builder
        .appName("AdventureWorks - Build Facts")
        .config(
            "spark.hadoop.fs.s3a.access.key",
            access_key
        )
        .config(
            "spark.hadoop.fs.s3a.secret.key",
            secret_key
        )
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    return spark


# =============================================================================
# READ
# =============================================================================

def read_table(spark, path):

    return spark.read.parquet(path)

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
# WRITE
# =============================================================================

def write_table(df, table):

    (
        df.write
        .format("jdbc")
        .option(
            "url",
            "jdbc:postgresql://postgres_gold_dw:5432/gold_dw"
        )
        .option("dbtable", table)
        .option("user", "gold_user")
        .option("password", "adminpassword")
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )

    print(f"[SUCCESS] gold/{table}")


# =============================================================================
# MAIN
# =============================================================================

def main():

    spark = init_spark()

    print("=" * 70)
    print("BUILD GOLD FACT TABLES")
    print("=" * 70)

    # ---------------------------------------------------------------------
    # Read Silver
    # ---------------------------------------------------------------------

    sales_header = read_table(
        spark,
        "s3a://silver/sales_order_header"
    )

    sales_detail = read_table(
        spark,
        "s3a://silver/sales_order_detail"
    )

    inventory = read_table(
        spark,
        "s3a://silver/product_inventory"
    )

    # ---------------------------------------------------------------------
    # Read Dimensions
    # ---------------------------------------------------------------------

    dim_customer = read_postgres_table(
        spark,
        "dim_customer"
    )

    dim_product = read_postgres_table(
        spark,
        "dim_product"
    )

    dim_geography = read_postgres_table(
        spark,
        "dim_geography"
    )

    dim_seller = read_postgres_table(
        spark,
        "dim_seller"
    )

    dim_date = read_postgres_table(
        spark,
        "dim_date"
    )

    # ---------------------------------------------------------------------
    # FACT ORDER
    # ---------------------------------------------------------------------

    print("\n[1/6] fact_order")

    fact = build_fact_order(
        sales_header,
        sales_detail,
        dim_customer,
        dim_product,
        dim_geography,
        dim_seller,
        dim_date
    )
    fact.printSchema()
    write_table(
        fact,
        "fact_order"
    )

    # ---------------------------------------------------------------------
    # FACT INVENTORY
    # ---------------------------------------------------------------------

    print("\n[2/6] fact_inventory")

    fact = build_fact_inventory(
        inventory,
        dim_product
    )
    fact.printSchema()
    write_table(
        fact,
        "fact_inventory"
    )

    # ---------------------------------------------------------------------
    # FACT CUSTOMER BEHAVIOR
    # ---------------------------------------------------------------------

    print("\n[3/6] fact_customer_behavior")

    fact = build_fact_customer_behavior(
        sales_header,
        sales_detail,
        dim_customer
    )
    fact.printSchema()  
    write_table(
        fact,
        "fact_customer_behavior"
    )

    # ---------------------------------------------------------------------
    # FACT PRODUCT DAILY
    # ---------------------------------------------------------------------

    print("\n[4/6] fact_product_daily")

    fact = build_fact_product_daily(
        sales_header,
        sales_detail,
        dim_product
    )
    fact.printSchema()
    write_table(
        fact,
        "fact_product_daily"
    )

    # ---------------------------------------------------------------------
    # FACT SELLER DAILY
    # ---------------------------------------------------------------------

    print("\n[5/6] fact_seller_daily")

    fact = build_fact_seller_daily(
        sales_header,
        sales_detail,
        dim_seller
    )
    fact.printSchema()
    write_table(
        fact,
        "fact_seller_daily"
    )

    # ---------------------------------------------------------------------
    # FACT ORDER DAILY
    # ---------------------------------------------------------------------

    print("\n[6/6] fact_order_daily")

    fact = build_fact_order_daily(
        sales_header,
        sales_detail
    )
    fact.printSchema()
    write_table(
        fact,
        "fact_order_daily"
    )

    print("\n" + "=" * 70)
    print("ALL FACT TABLES BUILT SUCCESSFULLY")
    print("=" * 70)

    spark.stop()


if __name__ == "__main__":

    main()