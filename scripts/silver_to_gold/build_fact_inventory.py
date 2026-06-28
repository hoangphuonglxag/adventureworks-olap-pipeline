# =============================================================================
# build_fact_inventory.py
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
        .appName("Build Gold - Fact Inventory")
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

def build_fact_inventory(
    inventory_df,
    product_dim
):

    fact = (

        inventory_df.alias("i")

        .join(
            product_dim.select(
                "product_key",
                "product_id"
            ),
            "product_id",
            "left"
        )

        .select(

            "product_key",

            "location_id",

            "shelf",

            "bin",

            F.col("quantity").alias("inventory_quantity")

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
        .option("dbtable", "fact_inventory")
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

    inventory = read_table(
        spark,
        "s3a://silver/product_inventory"
    )

    product = read_postgres_table(
        spark,
        "dim_product"
    )

    fact = build_fact_inventory(
        inventory,
        product
    )

    write_fact(fact)

    print(f"Inventory Rows : {fact.count()}")

    spark.stop()


if __name__ == "__main__":

    main()