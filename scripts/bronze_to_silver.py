# =============================================================================
# bronze_to_silver.py
# Bronze --> Silver ETL
# AdventureWorks2022
# =============================================================================

import os

from pyspark.sql import SparkSession

from business_cleaners import (
    clean_customer,
    clean_product,
    clean_geography,
    clean_sales_header,
    clean_sales_detail,
    clean_vendor,
    clean_seller
)


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
        .appName("AdventureWorks Bronze To Silver")
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

def read_table(spark, table):

    return spark.read.parquet(
        f"s3a://bronze/{table}"
    )


# =============================================================================
# WRITE
# =============================================================================

def write_table(df, table):

    (
        df.write
        .mode("overwrite")
        .option("compression", "snappy")
        .parquet(
            f"s3a://silver/{table}"
        )
    )

    print(f"[SUCCESS] silver/{table}")


# =============================================================================
# CUSTOMER
# =============================================================================

def process_customer(spark):

    print("Cleaning Customer...")

    customer = read_table(
        spark,
        "sales_customer"
    )

    person = read_table(
        spark,
        "person_person"
    )

    store = read_table(
        spark,
        "sales_store"
    )

    df = clean_customer(
        customer,
        person,
        store
    )

    write_table(
        df,
        "customer"
    )


# =============================================================================
# PRODUCT
# =============================================================================

def process_product(spark):

    print("Cleaning Product...")

    product = read_table(
        spark,
        "production_product"
    )

    subcategory = read_table(
        spark,
        "production_productsubcategory"
    )

    category = read_table(
        spark,
        "production_productcategory"
    )

    df = clean_product(
        product,
        subcategory,
        category
    )

    write_table(
        df,
        "product"
    )


# =============================================================================
# GEOGRAPHY
# =============================================================================

def process_geography(spark):

    print("Cleaning Geography...")

    address = read_table(
        spark,
        "person_address"
    )

    state = read_table(
        spark,
        "person_stateprovince"
    )

    country = read_table(
        spark,
        "person_countryregion"
    )

    territory = read_table(
        spark,
        "sales_salesterritory"
    )

    df = clean_geography(
        address,
        state,
        country,
        territory
    )

    write_table(
        df,
        "geography"
    )


# =============================================================================
# SALES HEADER
# =============================================================================

def process_sales_header(spark):

    print("Cleaning Sales Header...")

    df = read_table(
        spark,
        "sales_salesorderheader"
    )

    df = clean_sales_header(df)

    write_table(
        df,
        "sales_order_header"
    )


# =============================================================================
# SALES DETAIL
# =============================================================================

def process_sales_detail(spark):

    print("Cleaning Sales Detail...")

    df = read_table(
        spark,
        "sales_salesorderdetail"
    )

    df = clean_sales_detail(df)

    write_table(
        df,
        "sales_order_detail"
    )


# =============================================================================
# VENDOR
# =============================================================================

def process_vendor(spark):

    print("Cleaning Vendor...")

    df = read_table(
        spark,
        "purchasing_vendor"
    )

    df = clean_vendor(df)

    write_table(
        df,
        "vendor"
    )


# =============================================================================
# SELLER
# =============================================================================

def process_seller(spark):

    print("Cleaning Seller...")

    seller = read_table(
        spark,
        "sales_salesperson"
    )

    person = read_table(
        spark,
        "person_person"
    )

    df = clean_seller(
        seller,
        person
    )

    write_table(
        df,
        "seller"
    )


# =============================================================================
# MAIN
# =============================================================================

def main():

    spark = init_spark()

    print("=" * 60)
    print("AdventureWorks Bronze -> Silver")
    print("=" * 60)

    process_customer(spark)

    process_product(spark)

    process_geography(spark)

    process_sales_header(spark)

    process_sales_detail(spark)

    process_vendor(spark)

    process_seller(spark)

    spark.stop()

    print("=" * 60)
    print("Bronze -> Silver Completed")
    print("=" * 60)


if __name__ == "__main__":

    main()