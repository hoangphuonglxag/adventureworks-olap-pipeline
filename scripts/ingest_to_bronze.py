# =============================================================================
# BRONZE LAYER — Raw Ingestion from SQL Server
# =============================================================================
# Trích xuất 26 bảng từ AdventureWorks2022 (OLTP) và lưu dạng Parquet nén Snappy
# vào MinIO bucket "bronze/". Mỗi bảng = 1 folder riêng biệt.
#
# Bảng được phân 5 nhóm (Đã đồng bộ 100% phục vụ cho hệ thống 6 Dim + 6 Fact):
#   1. Customer & Geography  (9 bảng)  ← BỔ SUNG Sales.Store để lấy tên Đại lý B2B
#   2. Product               (5 bảng)
#   3. Sales                 (5 bảng)  
#   4. Inventory & Production(4 bảng)  
#   5. Purchasing & Vendor   (3 bảng)  
# =============================================================================

import os
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def init_spark() -> SparkSession:
    """
    Khởi tạo SparkSession.
    - spark-defaults.conf  : config hạ tầng S3A (endpoint, impl, ssl, jars)
    - Hàm này             : credentials nhạy cảm đọc từ env var
    """
    minio_access = os.environ.get("MINIO_ACCESS_KEY", "admin")
    minio_secret = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("AdventureWorks-Ingestion-Bronze")
        .config("spark.driver.host", "spark-master-engine")
        .config("spark.driver.bindAddress", "0.0.0.0")
        .config("spark.hadoop.fs.s3a.access.key", minio_access)
        .config("spark.hadoop.fs.s3a.secret.key", minio_secret)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def ingest_tables(spark, tables, bucket_name):   
    """
    Vòng lặp tự động cào danh sách bảng từ SQL Server -> MinIO Bronze.

    Each table is:
      1. Đọc qua JDBC từ SQL Server
      2. Gắn thêm cột metadata: _ingested_at (timestamp thời điểm chạy job)
      3. Ghi đè dạng Parquet nén Snappy vào s3a://bronze/<schema_table>/
    """
    jdbc_url = (
        "jdbc:sqlserver://sqlserver_source_oltp:1433;"
        "databaseName=AdventureWorks2022;"
        "encrypt=false;"
    )
    connection_props = {
        "user": "sa",
        "password": os.environ.get("SQLSERVER_PASSWORD", "AdminPassword123!"),
        "driver": "com.microsoft.sqlserver.jdbc.SQLServerDriver",
    }

    ingested_at = datetime.utcnow().isoformat()   # metadata chung cho cả batch
    success_tables: list[str] = []
    failed_tables:  list[str] = []

    for table in tables:
        print(f"\n[START] Đang cào bảng thô: {table} ...")
        try:
            # 1. Đọc từ SQL Server
            df = spark.read.jdbc(url=jdbc_url, table=table, properties=connection_props)
            row_count = df.count()
            print(f"       Tìm thấy {row_count:,} dòng")

            # 2. Gắn metadata timestamp
            df = df.withColumn("_ingested_at", F.lit(ingested_at))

            # 3. Định nghĩa đường dẫn lưu (Sales.Customer -> sales_customer)
            folder_name = table.replace(".", "_").lower()
            output_path = f"s3a://{bucket_name}/{folder_name}"

            # 4. Ghi Parquet (overwrite — idempotent)
            print(f"       Đang ghi Parquet -> {output_path}")
            (
                df.write
                .format("parquet")
                .option("compression", "snappy")
                .mode("overwrite")
                .save(output_path)
            )

            print(f"[SUCCESS] {table} -> {output_path}  ({row_count:,} rows)")
            success_tables.append(table)

        except Exception as exc:
            print(f"[ERROR]   {table}: {exc}")
            failed_tables.append(table)

    # ── Summary ──────────────────────────────────────────────────────────────
    sep = "=" * 65
    print(f"\n{sep}")
    print(f"[SUMMARY] Thành công: {len(success_tables)}/{len(tables)} bảng")
    if failed_tables:
        print(f"[SUMMARY] Thất bại  : {failed_tables}")
    print(sep)


# ─────────────────────────────────────────────────────────────────────────────
# DANH SÁCH 26 BẢNG BRONZE HOÀN CHỈNH (ĐÃ ĐỒNG BỘ CHUẨN)
# ─────────────────────────────────────────────────────────────────────────────
TABLES_TO_INGEST = [

    # ── Nhóm 1: Customer & Geography (9 bảng) ────────────────────────────────
    "Sales.Customer",                  # Bảng khách hàng chính (individual + store)
    "Sales.Store",                     # MỚI: Tên công ty/đại lý mua sỉ (B2B) -> Phục vụ gold.dim_customer
    "Person.Person",                    # Tên đầy đủ của khách lẻ cá nhân hoặc nhân viên
    "Person.BusinessEntityAddress",     # Liên kết Entity ↔ Address
    "Person.Address",                   # Địa chỉ chi tiết (Thành phố)
    "Person.StateProvince",             # Tỉnh/Bang
    "Person.CountryRegion",             # Quốc gia/Vùng
    "Person.EmailAddress",              # Email liên hệ
    "Person.PersonPhone",               # Số điện thoại liên hệ

    # ── Nhóm 2: Product (5 bảng) ─────────────────────────────────────────────
    "Production.Product",               # Bảng sản phẩm chính (standard cost, list price, reorder point)
    "Production.ProductSubcategory",    # Danh mục phụ
    "Production.ProductCategory",       # Danh mục chính
    "Production.ProductModel",          # Model sản phẩm
    "Production.ProductListPriceHistory",  # Lịch sử giá niêm yết

    # ── Nhóm 3: Sales (5 bảng) ───────────────────────────────────────────────
    "Sales.SalesOrderHeader",           # Header đơn hàng (kênh bán, ngày đặt, trạng thái)
    "Sales.SalesOrderDetail",           # Chi tiết từng dòng đơn bán (Doanh thu, lợi nhuận)
    "Sales.SalesTerritory",             # Khu vực bán hàng / Vùng chiến lược kinh doanh
    "Sales.SalesPerson",                # Nhân viên bán hàng + tỷ lệ hoa hồng
    "Sales.SalesPersonQuotaHistory",    # Chỉ tiêu doanh số (Quota) từng kỳ của nhân viên

    # ── Nhóm 4: Inventory & Production (4 bảng) ───────────────────────────────
    "Production.ProductInventory",      # Lượng tồn kho thực tế của sản phẩm theo từng vị trí kho
    "Production.Location",              # Tên gọi của các vị trí kho bãi (Tool Room, Paint Shop...)
    "Production.WorkOrder",             # Lệnh sản xuất 
    "Production.ScrapReason",           # Lý do phế phẩm 

    # ── Nhóm 5: Purchasing & Vendor (3 bảng) ──────────────────────────────────
    "Purchasing.Vendor",                # Nhà cung cấp (tên đối tác, mức uy tín tín dụng credit rating)
    "Purchasing.PurchaseOrderHeader",   # Header đơn mua vào từ nhà cung cấp
    "Purchasing.PurchaseOrderDetail",   # Chi tiết đơn mua (ReceivedQty, RejectedQty phục vụ Review Order)
]


if __name__ == "__main__":
    spark_sess = init_spark()
    ingest_tables(spark_sess, TABLES_TO_INGEST, bucket_name="bronze")
    spark_sess.stop()
    print("\n[FINISH] Toàn bộ 26 bảng thô đã được xử lý xong.")