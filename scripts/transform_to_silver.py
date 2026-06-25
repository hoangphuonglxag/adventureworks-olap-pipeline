# =============================================================================
# SILVER LAYER — Clean & Transform Job (Bronze Parquet → Silver Parquet)
# =============================================================================
import os
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def init_spark() -> SparkSession:
    """Khởi tạo SparkSession kết nối với hạ tầng MinIO S3A."""
    minio_access = os.environ.get("MINIO_ACCESS_KEY", "admin")
    minio_secret = os.environ.get("MINIO_SECRET_KEY", "adminpassword")

    spark = (
        SparkSession.builder
        .appName("AdventureWorks-Transformation-Silver")
        .config("spark.hadoop.fs.s3a.access.key", minio_access)
        .config("spark.hadoop.fs.s3a.secret.key", minio_secret)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def clean_customer(spark: SparkSession) -> None:
    """1. Xử lý Phân hệ Khách hàng (Dùng PersonType từ Person để phân loại chuẩn 100%)"""
    print("\n[SILVER] Đang làm sạch phân hệ Khách hàng...")
    
    df_cust = spark.read.parquet("s3a://bronze/sales_customer")
    df_person = spark.read.parquet("s3a://bronze/person_person")
    df_store = spark.read.parquet("s3a://bronze/sales_store")

    df_b2c_name = df_person.withColumn(
        "b2c_name",
        F.concat_ws(" ", F.trim(F.col("FirstName")), F.trim(F.col("MiddleName")), F.trim(F.col("LastName")))
    )

    c = df_cust.alias("c")
    p = df_b2c_name.alias("p")
    s = df_store.alias("s")

    df_join = c \
        .join(p, F.col("c.PersonID") == F.col("p.BusinessEntityID"), "left") \
        .join(s, F.col("c.StoreID") == F.col("s.BusinessEntityID"), "left")

    df_clean = df_join.withColumn(
        "customer_type_desc",
        F.when(F.col("p.PersonType") == "IN", "Individual")
         .when(F.col("p.PersonType") == "SC", "Store")
         .when(F.col("c.StoreID").isNotNull(), "Store")
         .otherwise("Individual")
    )

    df_result = df_clean \
        .withColumn("full_name", F.coalesce(F.col("p.b2c_name"), F.col("s.Name"))) \
        .select(
            F.col("c.CustomerID").alias("customer_id"),
            F.col("customer_type_desc").alias("customer_type"),
            F.col("full_name"),
            F.col("c._ingested_at")
        )

    df_result.write.mode("overwrite").parquet("s3a://silver/customer_cleaned")
    print("[SUCCESS] -> s3a://silver/customer_cleaned")


def clean_geolocation(spark: SparkSession) -> None:
    """2. Xử lý Phân hệ Địa lý (Phẳng hóa cây địa chỉ thành 1 bảng duy nhất có alias bảo vệ)"""
    print("\n[SILVER] Đang làm sạch phân hệ Địa lý...")
    
    df_addr = spark.read.parquet("s3a://bronze/person_address")
    df_state = spark.read.parquet("s3a://bronze/person_stateprovince")
    df_country = spark.read.parquet("s3a://bronze/person_countryregion")
    df_territory = spark.read.parquet("s3a://bronze/sales_salesterritory")

    addr = df_addr.alias("addr")
    st = df_state.alias("st")
    co = df_country.alias("co")
    te = df_territory.alias("te")

    df_clean = addr \
        .join(st, F.col("addr.StateProvinceID") == F.col("st.StateProvinceID"), "inner") \
        .join(co, F.col("st.CountryRegionCode") == F.col("co.CountryRegionCode"), "inner") \
        .join(te, F.col("st.TerritoryID") == F.col("te.TerritoryID"), "left") \
        .select(
            F.col("addr.AddressID").alias("address_id"),
            F.trim(F.col("addr.City")).alias("city"),
            F.col("st.Name").alias("state_province_name"),     
            F.col("co.Name").alias("country_region_name"),    
            F.col("te.Name").alias("territory_name"),         
            F.col("te.Group").alias("territory_group")
        )

    df_clean.write.mode("overwrite").parquet("s3a://silver/geolocation_cleaned")
    print("[SUCCESS] -> s3a://silver/geolocation_cleaned")


def clean_product(spark: SparkSession) -> None:
    """3. Xử lý Phân hệ Sản phẩm (JOIN Danh mục phụ/chính & Xử lý NULL Color/Size)"""
    print("\n[SILVER] Đang làm sạch phân hệ Sản phẩm...")
    
    df_prod = spark.read.parquet("s3a://bronze/production_product")
    df_sub = spark.read.parquet("s3a://bronze/production_productsubcategory")
    df_cat = spark.read.parquet("s3a://bronze/production_productcategory")

    prod = df_prod.alias("prod")
    sub = df_sub.alias("sub")
    cat = df_cat.alias("cat")

    df_clean = prod \
        .join(sub, F.col("prod.ProductSubcategoryID") == F.col("sub.ProductSubcategoryID"), "left") \
        .join(cat, F.col("sub.ProductCategoryID") == F.col("cat.ProductCategoryID"), "left") \
        .withColumn("color_clean", F.coalesce(F.col("prod.Color"), F.lit("N/A"))) \
        .withColumn("size_clean", F.coalesce(F.col("prod.Size"), F.lit("Universal"))) \
        .select(
            F.col("prod.ProductID").alias("product_id"),
            F.col("prod.Name").alias("product_name"),
            F.col("prod.ProductNumber").alias("product_number"),
            F.col("color_clean").alias("color"),
            F.col("size_clean").alias("size"),
            F.col("prod.StandardCost").cast("decimal(18,4)").alias("standard_cost"),
            F.col("prod.ListPrice").cast("decimal(18,4)").alias("list_price"),
            F.coalesce(F.col("cat.Name"), F.lit("N/A")).alias("category_name"),
            F.coalesce(F.col("sub.Name"), F.lit("N/A")).alias("subcategory_name"),
            F.col("prod.SafetyStockLevel").alias("safety_stock_level"),
            F.col("prod.ReorderPoint").alias("reorder_point")
        )

    df_clean.write.mode("overwrite").parquet("s3a://silver/product_cleaned")
    print("[SUCCESS] -> s3a://silver/product_cleaned")


def clean_sales_orders(spark: SparkSession) -> None:
    """4. Xử lý Đơn hàng Bán lẻ (Đồng bộ Kênh bán & Sửa tên cột Freight chuẩn nguồn)"""
    print("\n[SILVER] Đang làm sạch phân hệ Đơn hàng...")
    
    df_header = spark.read.parquet("s3a://bronze/sales_salesorderheader")
    df_detail = spark.read.parquet("s3a://bronze/sales_salesorderdetail")

    df_header_clean = df_header \
        .withColumn(
            "sales_channel",
            F.when(F.col("OnlineOrderFlag") == True, "Retail").otherwise("Reseller")
        ) \
        .withColumn(
            "sales_person_id_clean",
            F.coalesce(F.col("SalesPersonID"), F.lit(-1)) 
        )

    df_header_clean.select(
        F.col("SalesOrderID").alias("order_id"),
        F.col("OrderDate").alias("order_date"),
        F.col("CustomerID").alias("customer_id"),
        F.col("sales_person_id_clean").alias("sales_person_id"),
        F.col("TerritoryID").alias("territory_id"),
        F.col("sales_channel"),
        F.col("TotalDue").cast("decimal(18,4)").alias("total_due"),
        F.col("TaxAmt").cast("decimal(18,4)").alias("tax_amt"),
        F.col("Freight").cast("decimal(18,4)").alias("freight_amt"), 
        F.col("Status").alias("order_status")
    ).write.mode("overwrite").parquet("s3a://silver/sales_order_header_cleaned")

    df_detail.select(
        F.col("SalesOrderID").alias("order_id"),
        F.col("SalesOrderDetailID").alias("order_detail_id"),
        F.col("ProductID").alias("product_id"),
        F.col("OrderQty").alias("order_qty"),
        F.col("UnitPrice").cast("decimal(18,4)").alias("unit_price"),
        F.col("UnitPriceDiscount").cast("decimal(5,4)").alias("unit_price_discount"),
        F.col("LineTotal").cast("decimal(18,4)").alias("line_total")
    ).write.mode("overwrite").parquet("s3a://silver/sales_order_detail_cleaned")
    
    print("[SUCCESS] -> s3a://silver/sales_order_header_detail_cleaned")


if __name__ == "__main__":
    spark_sess = init_spark()
    
    # CHẠY ĐÚNG 4 HÀM ĐỘC LẬP TỪNG BƯỚC KHÔNG DƯ THỪA
    clean_customer(spark_sess)
    clean_geolocation(spark_sess)
    clean_product(spark_sess)
    clean_sales_orders(spark_sess)
    
    spark_sess.stop()
    print("\n[FINISH] Toàn bộ tầng Silver đã dọn rác và phẳng hóa thành công.")