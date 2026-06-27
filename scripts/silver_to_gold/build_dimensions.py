# =============================================================================
# build_dimensions.py
# Build All Gold Dimensions
# =============================================================================

import os

from pyspark.sql import SparkSession

from build_dim_date import build_dim_date
from build_dim_customer import build_dim_customer
from build_dim_product import build_dim_product
from build_dim_geography import build_dim_geography
from build_dim_vendor import build_dim_vendor
from build_dim_seller import build_dim_seller


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
        .appName("AdventureWorks - Build Dimensions")
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
# MAIN
# =============================================================================

def main():

    spark = init_spark()

    print("=" * 70)
    print("BUILD GOLD DIMENSIONS")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # Dimension Date
    # -------------------------------------------------------------------------
    print("\n[1/6] Building dim_date ...")

    dim_date = build_dim_date(
        spark,
        start_date="2010-01-01",
        end_date="2030-12-31"
    )

    (
        dim_date.write
        .format("jdbc")
        .option("url", "jdbc:postgresql://postgres_gold_dw:5432/gold_dw")
        .option("dbtable", "dim_date")
        .option("user", "gold_user")
        .option("password", "adminpassword")
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )

    print("✓ dim_date completed")


    # -------------------------------------------------------------------------
    # Dimension Customer
    # -------------------------------------------------------------------------
    print("\n[2/6] Building dim_customer ...")

    customer = spark.read.parquet(
        "s3a://silver/customer"
    )

    dim_customer = build_dim_customer(customer)

    (
        dim_customer.write
        .format("jdbc")
        .option("url", "jdbc:postgresql://postgres_gold_dw:5432/gold_dw")
        .option("dbtable", "dim_customer")
        .option("user", "gold_user")
        .option("password", "adminpassword")
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )

    print("✓ dim_customer completed")


    # -------------------------------------------------------------------------
    # Dimension Product
    # -------------------------------------------------------------------------
    print("\n[3/6] Building dim_product ...")

    product = spark.read.parquet(
        "s3a://silver/product"
    )

    dim_product = build_dim_product(product)

    (
        dim_product.write
        .format("jdbc")
        .option("url", "jdbc:postgresql://postgres_gold_dw:5432/gold_dw")
        .option("dbtable", "dim_product")
        .option("user", "gold_user")
        .option("password", "adminpassword")
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )

    print("✓ dim_product completed")


    # -------------------------------------------------------------------------
    # Dimension Geography
    # -------------------------------------------------------------------------
    print("\n[4/6] Building dim_geography ...")

    geography = spark.read.parquet(
        "s3a://silver/geography"
    )

    dim_geography = build_dim_geography(
        geography
    )

    (
        dim_geography.write
        .format("jdbc")
        .option("url", "jdbc:postgresql://postgres_gold_dw:5432/gold_dw")
        .option("dbtable", "dim_geography")
        .option("user", "gold_user")
        .option("password", "adminpassword")
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )

    print("✓ dim_geography completed")


    # -------------------------------------------------------------------------
    # Dimension Vendor
    # -------------------------------------------------------------------------
    print("\n[5/6] Building dim_vendor ...")

    vendor = spark.read.parquet(
        "s3a://silver/vendor"
    )

    dim_vendor = build_dim_vendor(vendor)

    (
        dim_vendor.write
        .format("jdbc")
        .option("url", "jdbc:postgresql://postgres_gold_dw:5432/gold_dw")
        .option("dbtable", "dim_vendor")
        .option("user", "gold_user")
        .option("password", "adminpassword")
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )

    print("✓ dim_vendor completed")


    # -------------------------------------------------------------------------
    # Dimension Seller
    # -------------------------------------------------------------------------
    print("\n[6/6] Building dim_seller ...")

    seller = spark.read.parquet(
        "s3a://silver/seller"
    )

    dim_seller = build_dim_seller(
        seller
    )

    (
        dim_seller.write
        .format("jdbc")
        .option("url", "jdbc:postgresql://postgres_gold_dw:5432/gold_dw")
        .option("dbtable", "dim_seller")
        .option("user", "gold_user")
        .option("password", "adminpassword")
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )

    print("✓ dim_seller completed")


    print("\n" + "=" * 70)
    print("ALL DIMENSIONS BUILT SUCCESSFULLY")
    print("=" * 70)

    spark.stop()


if __name__ == "__main__":
    main()