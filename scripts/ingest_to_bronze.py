import os
import sys
from pyspark.sql import SparkSession

def init_spark():
    """Khởi tạo Spark Session với đầy đủ cấu hình MinIO S3A và fix hostname"""
    spark = SparkSession.builder \
        .appName("AdventureWorks-Ingestion-Bronze") \
        .config("spark.driver.host", "spark-master-engine") \
        .config("spark.driver.bindAddress", "0.0.0.0") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
        .config("spark.hadoop.fs.s3a.access.key", "admin") \
        .config("spark.hadoop.fs.s3a.secret.key", "adminpassword") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.aws.credentials.provider", "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .getOrCreate()
    return spark

def ingest_tables(spark, tables, bucket_name):
    """Vòng lặp tự động cào danh sách bảng từ SQL Server sang MinIO Bronze"""
    jdbc_url = "jdbc:sqlserver://sqlserver_source_oltp:1433;databaseName=AdventureWorks2022;encrypt=false;"
    connection_properties = {
        "user": "sa",
        "password": "AdminPassword123!",
        "driver": "com.microsoft.sqlserver.jdbc.SQLServerDriver"
    }
    
    for table in tables:
        print(f"\n[START] Đang tiến hành cào bảng thô: {table} ...")
        try:
            # 1. Đọc dữ liệu từ SQL Server nguồn qua JDBC
            df = spark.read.jdbc(url=jdbc_url, table=table, properties=connection_properties)
            
            # Đếm nhanh số dòng check log cho sướng mắt
            row_count = df.count()
            print(f"Tìm thấy {row_count} dòng trong bảng {table}")
            
            # 2. Định nghĩa tên folder lưu trữ trên MinIO (Ví dụ: Sales.Customer -> sales_customer)
            folder_name = table.replace(".", "_").lower()
            output_path = f"s3a://{bucket_name}/{folder_name}"
            
            # 3. Ghi dữ liệu xuống dạng Parquet nén Snappy (Chế độ ghi đè - Idempotent)
            print(f"Đang nén file Parquet và đẩy vào bucket {bucket_name} -> {output_path}...")
            df.write \
              .format("parquet") \
              .option("compression", "snappy") \
              .mode("overwrite") \
              .save(output_path)
              
            print(f"[SUCCESS] Bảng {table} đã được lưu thành công vào {output_path}")
            
        except Exception as e:
            print(f"[ERROR] Lỗi khi xử lý bảng {table}: {str(e)}")
            continue 

if __name__ == "__main__":
    spark_sess = init_spark()
    
    # (Customer + Product + Sales)
    tables_to_ingest = [
        # 1. Cụm Khách hàng & Địa lý
        "Sales.Customer",
        "Person.Person",
        "Person.EmailAddress",
        "Person.PersonPhone",
        "Person.BusinessEntityAddress",
        "Person.Address",
        "Person.StateProvince",
        "Person.CountryRegion", 
        # 2. Cụm Sản phẩm
        "Production.Product",
        "Production.ProductSubcategory",
        "Production.ProductCategory",
        "Production.ProductModel",
        # 3. Cụm Đơn hàng
        "Sales.SalesOrderHeader",
        "Sales.SalesOrderDetail",
        "Sales.SalesTerritory"
    ]
    ingest_tables(spark_sess, tables_to_ingest, "bronze")
    
    spark_sess.stop()
    print("\n[FINISH] Toàn bộ các bảng thô đã được xử lý")