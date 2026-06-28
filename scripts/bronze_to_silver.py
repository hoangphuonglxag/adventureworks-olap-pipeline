# =============================================================================
# bronze_to_silver.py
# Bronze --> Silver ETL (With Advanced Auditing Log)
# AdventureWorks2022
# =============================================================================

import os
import time
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

# Biến toàn cục để lưu lại báo cáo cuối pipeline
JOB_REPORT = []

# =============================================================================
# SPARK
# =============================================================================

def init_spark():
    access_key = os.environ.get("MINIO_ACCESS_KEY", "admin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("AdventureWorks Bronze To Silver")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .getOrCreate()
    )

    # ÉP LOG LEVEL XUỐNG ERROR để chặn đứng đống log INFO rác của Spark
    spark.sparkContext.setLogLevel("ERROR")
    return spark


# =============================================================================
# READ / WRITE UTILITIES WITH AUDITING
# =============================================================================

def read_table(spark, table):
    return spark.read.parquet(f"s3a://bronze/{table}")


def write_table(df, table, source_count):
    """Ghi dữ liệu đồng thời tính toán số lượng để làm báo cáo log"""
    start_time = time.time()
    
    # Đếm số dòng thực tế ghi xuống Silver sau khi đã lọc rác
    sink_count = df.count()
    missed_count = source_count - sink_count
    
    (
        df.write
        .mode("overwrite")
        .option("compression", "snappy")
        .parquet(f"s3a://silver/{table}")
    )
    
    duration = round(time.time() - start_time, 2)
    
    # Lưu thông tin vào bảng báo cáo
    JOB_REPORT.append({
        "Table": table,
        "Source Rows": source_count,
        "Silver Rows": sink_count,
        "Missed/Filtered": missed_count,
        "Duration (s)": duration
    })


# =============================================================================
# TRANSFORMATIONS
# =============================================================================

def process_customer(spark, person_df, person_count):
    customer = read_table(spark, "sales_customer")
    store = read_table(spark, "sales_store")
    
    # Lấy tổng dòng của bảng gốc (Bảng chính quyết định số dòng)
    source_count = customer.count()

    df = clean_customer(customer, person_df, store)
    write_table(df, "customer", source_count)


def process_product(spark):
    product = read_table(spark, "production_product")
    subcategory = read_table(spark, "production_productsubcategory")
    category = read_table(spark, "production_productcategory")
    
    source_count = product.count()
    df = clean_product(product, subcategory, category)
    write_table(df, "product", source_count)


def process_geography(spark):
    address = read_table(spark, "person_address")
    state = read_table(spark, "person_stateprovince")
    country = read_table(spark, "person_countryregion")
    territory = read_table(spark, "sales_salesterritory")
    
    source_count = address.count()
    df = clean_geography(address, state, country, territory)
    write_table(df, "geography", source_count)


def process_sales_header(spark):
    df = read_table(spark, "sales_salesorderheader")
    source_count = df.count()
    df = clean_sales_header(df)
    write_table(df, "sales_order_header", source_count)


def process_sales_detail(spark):
    df = read_table(spark, "sales_salesorderdetail")
    source_count = df.count()
    df = clean_sales_detail(df)
    write_table(df, "sales_order_detail", source_count)


def process_vendor(spark):
    df = read_table(spark, "purchasing_vendor")
    source_count = df.count()
    df = clean_vendor(df)
    write_table(df, "vendor", source_count)


def process_seller(spark, person_df):
    seller = read_table(spark, "sales_salesperson")
    source_count = seller.count()
    df = clean_seller(seller, person_df)
    write_table(df, "seller", source_count)


# =============================================================================
# PRINT DASHBOARD REPORT
# =============================================================================
def print_summary_dashboard():
    print("\n" + "="*85)
    print(f"{'ADVENTUREWORKS PIPELINE MONITORING DASHBOARD':^85}")
    print("="*85)
    print(f"| {'Table Name':<22} | {'Source Rows':<12} | {'Silver Rows':<12} | {'Filtered':<10} | {'Time (s)':<8} |")
    print("-"*85)
    
    for row in JOB_REPORT:
        print(f"| {row['Table']:<22} | {row['Source Rows']:<12,} | {row['Silver Rows']:<12,} | {row['Missed/Filtered']:<10,} | {row['Duration (s)']:<8} |")
        
    print("="*85)


# =============================================================================
# MAIN
# =============================================================================

def main():
    spark = init_spark()

    print("\n>>> Pipeline Started. Processing layers, please wait...")

    # Đọc và đếm bảng dùng chung một lần
    shared_person = read_table(spark, "person_person")
    person_count = shared_person.count()

    # Kích hoạt các pipeline xử lý
    process_customer(spark, shared_person, person_count)
    process_product(spark)
    process_geography(spark)
    process_sales_header(spark)
    process_sales_detail(spark)
    process_vendor(spark)
    process_seller(spark, shared_person)

    # In kết quả dạng bảng xịn sò
    print_summary_dashboard()

    spark.stop()


if __name__ == "__main__":
    main()