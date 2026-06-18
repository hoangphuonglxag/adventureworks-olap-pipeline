# scripts/spark_utils.py
# =============================================================================
# SHARED SPARK SESSION HELPER
# =============================================================================
# Dùng chung cho tất cả các script trong pipeline (ingest, transform, load).
# Config S3A và JARs đọc từ spark-defaults.conf — không hardcode ở đây.
# =============================================================================
import os
from pyspark.sql import SparkSession

def get_spark_session(app_name: str = "AdventureWorks-Pipeline") -> SparkSession:
    """
    Tạo hoặc lấy lại SparkSession đang chạy.

    - Kết nối vào Spark standalone cluster (spark-master-engine:7077)
    - Mọi config S3A, JARs đã khai báo trong spark-defaults.conf
    - Chỉ set các config network cần thiết để driver tìm được master

    Args:
        app_name: Tên hiển thị trên Spark UI (nên truyền tên job cụ thể)

    Returns:
        SparkSession đã được khởi tạo
    """
    spark = SparkSession.builder \
        .appName(app_name) \
        .config("spark.driver.host", "spark-master-engine") \
        .config("spark.driver.bindAddress", "0.0.0.0") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")
    return spark