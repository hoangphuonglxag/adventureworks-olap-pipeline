"""
build_customer_segmentation_dataset.py

ETL job:
  SQL Server (AdventureWorks2022 OLTP)  --JDBC-->  Spark  --transform-->  MinIO (s3a://silver/customer_segmentation)

1 row = 1 customer. Output is used downstream for K-Means clustering (Customer Segmentation).

Run inside the spark_master_engine container via spark-submit:
    /opt/spark/bin/spark-submit /opt/spark/scripts/build_customer_segmentation_dataset.py
"""

import os
import sys
import logging
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("build_customer_segmentation_dataset")

# --------------------------------------------------------------------------
# Config
# Read credentials from environment variables (already injected into the
# spark-master / spark-worker containers via env_file / environment in
# docker-compose.yml: MINIO_ACCESS_KEY, MINIO_SECRET_KEY, SQLSERVER_PASSWORD).
# --------------------------------------------------------------------------

# Spark cluster master (matches spark-master service: hostname spark-master-engine, port 7077)
SPARK_MASTER_URL = os.environ.get("SPARK_MASTER_URL", "spark://spark-master-engine:7077")

# SQL Server source (container_name: sqlserver_source_oltp)
SQLSERVER_HOST = os.environ.get("SQLSERVER_HOST", "sqlserver_source_oltp")
SQLSERVER_PORT = os.environ.get("SQLSERVER_PORT", "1433")
SQLSERVER_DB = os.environ.get("SQLSERVER_DB", "AdventureWorks2022")
JDBC_URL = (
    f"jdbc:sqlserver://{SQLSERVER_HOST}:{SQLSERVER_PORT};"
    f"databaseName={SQLSERVER_DB};encrypt=true;trustServerCertificate=true"
)
JDBC_DRIVER = "com.microsoft.sqlserver.jdbc.SQLServerDriver"

JDBC_USER = os.environ.get("SQLSERVER_USER", "sa")
JDBC_PASSWORD = os.environ["SQLSERVER_PASSWORD"]  # required, injected via .env

# MinIO (S3A) — endpoint is also set in spark-defaults.conf; env vars below are
# the same credentials already used by the container per docker-compose.yml.
MINIO_ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
MINIO_ENDPOINT = "http://minio:9000"

OUTPUT_PATH = "s3a://silver/customer_segmentation/"


def get_spark_session() -> SparkSession:
    """Create and configure SparkSession, pointed at the Spark cluster master,
    with S3A (MinIO) settings."""
    spark = (
        SparkSession.builder
        .appName("build_customer_segmentation_dataset")
        .master(SPARK_MASTER_URL)
        .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY)
        .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def read_jdbc_table(spark: SparkSession, dbtable: str):
    """Read a single table from SQL Server via Spark JDBC."""
    logger.info("Loading table from SQL Server: %s", dbtable)
    df = (
        spark.read.format("jdbc")
        .option("url", JDBC_URL)
        .option("dbtable", dbtable)
        .option("driver", JDBC_DRIVER)
        .option("user", JDBC_USER)
        .option("password", JDBC_PASSWORD)
        .load()
    )
    row_count = df.count()
    logger.info("Loaded %s -> %d rows", dbtable, row_count)
    return df


def main():
    start_ts = datetime.now()
    logger.info("=== Job started at %s ===", start_ts.isoformat())

    spark = get_spark_session()

    try:
        # ------------------------------------------------------------
        # 1. Load source tables (mandatory core tables)
        # ------------------------------------------------------------
        customer_df = read_jdbc_table(spark, "Sales.Customer")
        sales_order_header_df = read_jdbc_table(spark, "Sales.SalesOrderHeader")
        sales_order_detail_df = read_jdbc_table(spark, "Sales.SalesOrderDetail")
        sales_territory_df = read_jdbc_table(spark, "Sales.SalesTerritory")

        # ------------------------------------------------------------
        # 2. Join: Customer -> SalesOrderHeader -> SalesOrderDetail -> SalesTerritory
        # ------------------------------------------------------------
        customer_slim = customer_df.select(
            F.col("CustomerID"),
            F.col("TerritoryID"),
        )

        territory_slim = sales_territory_df.select(
            F.col("TerritoryID"),
            F.col("Name").alias("TerritoryName"),
        )

        header_slim = sales_order_header_df.select(
            F.col("SalesOrderID"),
            F.col("CustomerID"),
            F.col("OrderDate"),
            F.col("TotalDue"),
        )

        detail_slim = sales_order_detail_df.select(
            F.col("SalesOrderID"),
            F.col("ProductID"),
            F.col("OrderQty"),
            F.col("UnitPriceDiscount"),
        )

        joined_df = (
            customer_slim
            .join(territory_slim, on="TerritoryID", how="left")
            .join(header_slim, on="CustomerID", how="inner")
            .join(detail_slim, on="SalesOrderID", how="inner")
        )

        joined_df = joined_df.cache()
        logger.info("Joined dataset row count: %d", joined_df.count())

        # ------------------------------------------------------------
        # 3. Compute global max OrderDate (anchor date for Recency)
        # ------------------------------------------------------------
        max_order_date_row = joined_df.agg(F.max("OrderDate").alias("max_date")).collect()[0]
        max_order_date = max_order_date_row["max_date"]
        logger.info("Max OrderDate in dataset (recency anchor): %s", max_order_date)

        # ------------------------------------------------------------
        # 4. Group by CustomerID -> aggregate features
        # ------------------------------------------------------------
        agg_df = (
            joined_df.groupBy("CustomerID", "TerritoryName")
            .agg(
                F.countDistinct("SalesOrderID").alias("TotalOrders"),
                # TotalDue is per-order (header level); to avoid double counting
                # across joined detail rows, sum distinct (SalesOrderID, TotalDue) pairs instead.
                F.sum("OrderQty").alias("TotalQuantity"),
                F.countDistinct("ProductID").alias("DistinctProducts"),
                F.max("OrderDate").alias("LastOrderDate"),
                F.avg("UnitPriceDiscount").alias("AvgDiscount"),
            )
        )

        # TotalSpent / AvgOrderValue must be computed from distinct
        # (SalesOrderID, TotalDue) pairs to avoid inflation from the
        # one-to-many join with SalesOrderDetail.
        order_value_df = (
            joined_df.select("CustomerID", "SalesOrderID", "TotalDue")
            .distinct()
            .groupBy("CustomerID")
            .agg(
                F.sum("TotalDue").alias("TotalSpent"),
                F.avg("TotalDue").alias("AvgOrderValue"),
            )
        )

        agg_df = agg_df.join(order_value_df, on="CustomerID", how="left")

        # ------------------------------------------------------------
        # 5. Compute RecencyDays = max(OrderDate) - LastOrderDate(customer)
        # ------------------------------------------------------------
        agg_df = agg_df.withColumn(
            "RecencyDays",
            F.datediff(F.lit(max_order_date), F.col("LastOrderDate")).cast("int"),
        )

        # ------------------------------------------------------------
        # 6. Select final schema + fill nulls
        # ------------------------------------------------------------
        final_df = agg_df.select(
            F.col("CustomerID").cast("int"),
            F.col("TerritoryName").cast("string"),
            F.col("TotalOrders").cast("int"),
            F.col("TotalSpent").cast("double"),
            F.col("AvgOrderValue").cast("double"),
            F.col("TotalQuantity").cast("int"),
            F.col("DistinctProducts").cast("int"),
            F.col("RecencyDays").cast("int"),
            F.col("AvgDiscount").cast("double"),
        )

        numeric_fill = {
            "TotalOrders": 0,
            "TotalSpent": 0.0,
            "AvgOrderValue": 0.0,
            "TotalQuantity": 0,
            "DistinctProducts": 0,
            "RecencyDays": 0,
            "AvgDiscount": 0.0,
        }
        string_fill = {"TerritoryName": "Unknown"}

        final_df = final_df.na.fill(numeric_fill).na.fill(string_fill)

        final_count = final_df.count()
        logger.info("Final customer segmentation dataset row count: %d", final_count)

        # ------------------------------------------------------------
        # 7. Write to MinIO (Silver layer) - Parquet, Snappy, overwrite
        # ------------------------------------------------------------
        logger.info("Writing dataset to %s", OUTPUT_PATH)
        (
            final_df.write
            .mode("overwrite")
            .format("parquet")
            .option("compression", "snappy")
            .save(OUTPUT_PATH)
        )

        end_ts = datetime.now()
        duration = (end_ts - start_ts).total_seconds()
        logger.info("=== Job finished at %s | duration: %.2fs ===", end_ts.isoformat(), duration)
        logger.info(
            "Summary | Customer rows: %d | SalesOrderHeader rows: %d | "
            "SalesOrderDetail rows: %d | SalesTerritory rows: %d | Final dataset rows: %d",
            customer_df.count(),
            sales_order_header_df.count(),
            sales_order_detail_df.count(),
            sales_territory_df.count(),
            final_count,
        )

    except Exception as e:
        logger.error("Job failed: %s", str(e), exc_info=True)
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
