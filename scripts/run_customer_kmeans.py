"""
run_customer_kmeans.py

Read customer segmentation dataset from MinIO
Run KMeans clustering with hyperparameter search (k, initMode, distanceMeasure, seed)
Evaluate every configuration (Silhouette + WSSSE)
Pick the best configuration automatically
Write clustered output, best model, and full comparison report back to MinIO
"""

import os
import logging
import json
import itertools

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator

# --------------------------------------------------
# Logging
# --------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kmeans")

# --------------------------------------------------
# Paths
# --------------------------------------------------
INPUT_PATH = "s3a://silver/customer_segmentation/"
OUTPUT_PATH = "s3a://gold/customer_segments/"
METRICS_PATH = "s3a://gold/models/kmeans_customer/metrics/"
SEARCH_REPORT_PATH = "s3a://gold/models/kmeans_customer/search_report/"
MODEL_PATH = "s3a://gold/models/kmeans_customer/model/"

# --------------------------------------------------
# MinIO config
# --------------------------------------------------
MINIO_ENDPOINT = "http://minio:9000"
MINIO_ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = os.environ["MINIO_SECRET_KEY"]

SPARK_MASTER_URL = os.environ.get(
    "SPARK_MASTER_URL",
    "spark://spark-master-engine:7077"
)

# --------------------------------------------------
# Hyperparameter search space
# --------------------------------------------------
# Mở rộng / thu hẹp tuỳ thời gian chạy cho phép. Mỗi tổ hợp sẽ train + evaluate
# 1 lần, nên số tổ hợp càng nhiều thì thời gian chạy càng lâu.
# Bỏ k=2 mặc định vì với dữ liệu lệch (outlier), k=2 gần như luôn chỉ tách
# "khách hàng bình thường" ra khỏi "vài khách hàng cực đoan" -> silhouette ảo cao.
K_VALUES = [3, 4, 5, 6, 7, 8]
INIT_MODES = ["k-means||", "random"]
DISTANCE_MEASURES = ["euclidean", "cosine"]
SEEDS = [42]  # thêm nhiều seed nếu muốn kiểm tra độ ổn định, vd [42, 7, 123]
MAX_ITER = 50          # tăng nếu mô hình chưa hội tụ
TOL = 1e-4

# Các cột bị lệch (skewed) thường có vài khách hàng/giá trị cực lớn (vd mua rất
# nhiều, chi tiêu rất cao). Nếu không xử lý, KMeans (dựa trên khoảng cách) sẽ
# tách hẳn các outlier này thành cụm riêng thay vì phân khúc khách hàng thực sự,
# khiến silhouette cao "ảo" nhưng phân cụm vô nghĩa về mặt kinh doanh.
# log1p kéo các giá trị lớn lại gần phân phối chính mà vẫn giữ thứ tự.
LOG_TRANSFORM_COLS = [
    "TotalSpent",
    "AvgOrderValue",
    "TotalQuantity",
    "TotalOrders",
    "RecencyDays",
]

# Tiêu chí chọn cấu hình tốt nhất: "silhouette" (càng cao càng tốt)
# Có thể đổi sang "wssse" nếu chỉ quan tâm độ chặt cụm (càng thấp càng tốt),
# nhưng silhouette phản ánh chất lượng phân tách cụm tốt hơn.
SELECTION_METRIC = "silhouette"

# Ràng buộc cân bằng cụm: loại các cấu hình có cụm nhỏ nhất chiếm dưới
# MIN_CLUSTER_FRACTION tổng số khách hàng, để tránh chọn nhầm giải pháp kiểu
# "1 cụm khổng lồ + vài cụm outlier vài chục khách" dù silhouette cao ảo.
# Tăng giá trị này nếu vẫn còn cụm quá nhỏ; giảm nếu bạn THỰC SỰ muốn tìm các
# phân khúc khách hàng VIP/hiếm (số lượng ít nhưng có ý nghĩa kinh doanh).
MIN_CLUSTER_FRACTION = 0.03


# --------------------------------------------------
# Spark session
# --------------------------------------------------
def get_spark():
    return (
        SparkSession.builder
        .appName("customer-kmeans-search")
        .master(SPARK_MASTER_URL)
        .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY)
        .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .getOrCreate()
    )


# --------------------------------------------------
# Load + feature engineering (chạy 1 lần, dùng chung cho mọi cấu hình)
# --------------------------------------------------
def load_and_prepare(spark):
    logger.info("Loading dataset...")
    df = spark.read.parquet(INPUT_PATH)

    feature_cols = [
        "TotalOrders",
        "TotalSpent",
        "AvgOrderValue",
        "TotalQuantity",
        "DistinctProducts",
        "RecencyDays",
        "AvgDiscount",
    ]

    df = df.fillna(0)

    # Log-transform các cột bị lệch để giảm ảnh hưởng của outlier lên khoảng
    # cách Euclidean (xem giải thích ở LOG_TRANSFORM_COLS phía trên).
    for col_name in LOG_TRANSFORM_COLS:
        if col_name in feature_cols:
            df = df.withColumn(col_name, F.log1p(F.col(col_name).cast("double")))

    assembler = VectorAssembler(
        inputCols=feature_cols,
        outputCol="features_raw"
    )
    assembled = assembler.transform(df)

    scaler = StandardScaler(
        inputCol="features_raw",
        outputCol="features",
        withMean=True,
        withStd=True
    )
    scaler_model = scaler.fit(assembled)
    scaled_df = scaler_model.transform(assembled)

    # Cache vì sẽ được dùng lại nhiều lần qua các vòng lặp grid search
    scaled_df = scaled_df.cache()
    scaled_df.count()  # trigger cache

    return scaled_df


# --------------------------------------------------
# Train + evaluate một cấu hình
# --------------------------------------------------
def run_single_config(scaled_df, k, init_mode, distance_measure, seed):
    kmeans = KMeans(
        k=k,
        seed=seed,
        featuresCol="features",
        predictionCol="cluster",
        initMode=init_mode,
        distanceMeasure=distance_measure,
        maxIter=MAX_ITER,
        tol=TOL,
    )

    model = kmeans.fit(scaled_df)
    result = model.transform(scaled_df)

    evaluator = ClusteringEvaluator(
        featuresCol="features",
        predictionCol="cluster",
        metricName="silhouette",
        distanceMeasure="squaredEuclidean" if distance_measure == "euclidean" else "cosine",
    )

    silhouette = evaluator.evaluate(result)
    wssse = model.summary.trainingCost

    cluster_dist = (
        result.groupBy("cluster")
        .count()
        .orderBy("cluster")
        .collect()
    )

    # Cảnh báo nếu có cụm quá nhỏ (gợi ý k đang quá lớn / không ổn định)
    min_cluster_size = min(r["count"] for r in cluster_dist)

    config_result = {
        "k": k,
        "initMode": init_mode,
        "distanceMeasure": distance_measure,
        "seed": seed,
        "silhouette": float(silhouette),
        "wssse": float(wssse),
        "min_cluster_size": int(min_cluster_size),
        "clusters": {str(r["cluster"]): int(r["count"]) for r in cluster_dist},
    }

    logger.info(
        f"[k={k:>2} | init={init_mode:>10} | dist={distance_measure:>9} | seed={seed}] "
        f"silhouette={silhouette:.4f}  wssse={wssse:.2f}  min_cluster={min_cluster_size}"
    )

    return config_result, model, result


# --------------------------------------------------
# Grid search chính
# --------------------------------------------------
def grid_search(scaled_df):
    all_results = []
    best = None
    best_model = None
    best_result_df = None

    total_customers = scaled_df.count()
    min_cluster_size_allowed = int(total_customers * MIN_CLUSTER_FRACTION)
    logger.info(
        f"Tổng số khách hàng: {total_customers}. "
        f"Yêu cầu cụm nhỏ nhất >= {min_cluster_size_allowed} "
        f"({MIN_CLUSTER_FRACTION:.0%} tổng số) để được xét là cấu hình hợp lệ."
    )

    combos = list(itertools.product(K_VALUES, INIT_MODES, DISTANCE_MEASURES, SEEDS))
    logger.info(f"Bắt đầu grid search với {len(combos)} tổ hợp tham số...")

    for k, init_mode, distance_measure, seed in combos:
        try:
            config_result, model, result_df = run_single_config(
                scaled_df, k, init_mode, distance_measure, seed
            )
        except Exception as e:
            logger.warning(
                f"Bỏ qua cấu hình k={k}, init={init_mode}, dist={distance_measure}, "
                f"seed={seed} do lỗi: {e}"
            )
            continue

        all_results.append(config_result)

        # Loại các cấu hình tạo cụm outlier quá nhỏ, dù silhouette/wssse có đẹp
        # đến đâu -> tránh chọn nhầm "1 cụm to + cụm outlier vài chục khách".
        if config_result["min_cluster_size"] < min_cluster_size_allowed:
            logger.info(
                f"  -> Loại (cụm nhỏ nhất {config_result['min_cluster_size']} "
                f"< ngưỡng {min_cluster_size_allowed})"
            )
            continue

        is_better = (
            best is None
            or (
                SELECTION_METRIC == "silhouette"
                and config_result["silhouette"] > best["silhouette"]
            )
            or (
                SELECTION_METRIC == "wssse"
                and config_result["wssse"] < best["wssse"]
            )
        )

        if is_better:
            best = config_result
            best_model = model
            best_result_df = result_df

    if best is None:
        logger.warning(
            "Không có cấu hình nào thoả ràng buộc cân bằng cụm. "
            "Sẽ chọn cấu hình tốt nhất theo silhouette trong số tất cả kết quả "
            "(kể cả cụm mất cân bằng) -- cân nhắc giảm MIN_CLUSTER_FRACTION hoặc "
            "kiểm tra lại outlier trong dữ liệu."
        )
        for config_result in all_results:
            is_better = (
                best is None
                or (
                    SELECTION_METRIC == "silhouette"
                    and config_result["silhouette"] > best["silhouette"]
                )
                or (
                    SELECTION_METRIC == "wssse"
                    and config_result["wssse"] < best["wssse"]
                )
            )
            if is_better:
                best = config_result
        # Train lại cấu hình fallback này để lấy model/result_df tương ứng
        best, best_model, best_result_df = run_single_config(
            scaled_df, best["k"], best["initMode"], best["distanceMeasure"], best["seed"]
        )

    return all_results, best, best_model, best_result_df


# --------------------------------------------------
# Main pipeline
# --------------------------------------------------
def main():
    spark = get_spark()

    scaled_df = load_and_prepare(spark)

    all_results, best, best_model, best_result_df = grid_search(scaled_df)

    if best is None:
        raise RuntimeError("Không có cấu hình nào chạy thành công. Kiểm tra lại dữ liệu/tham số.")

    logger.info("========== KẾT QUẢ TỐT NHẤT ==========")
    logger.info(f"k                = {best['k']}")
    logger.info(f"initMode         = {best['initMode']}")
    logger.info(f"distanceMeasure  = {best['distanceMeasure']}")
    logger.info(f"seed             = {best['seed']}")
    logger.info(f"Silhouette Score = {best['silhouette']:.4f}")
    logger.info(f"WSSSE (Inertia)  = {best['wssse']:.2f}")
    logger.info(f"Cụm nhỏ nhất     = {best['min_cluster_size']} khách hàng")
    logger.info("Phân bố cụm:")
    for cid, cnt in sorted(best["clusters"].items(), key=lambda x: int(x[0])):
        logger.info(f"  Cluster {cid} -> {cnt} customers")
    logger.info("=======================================")

    # --------------------------------------------------
    # Ghi dữ liệu đã gán cụm (theo mô hình tốt nhất)
    # --------------------------------------------------
    final = best_result_df.select(
        "CustomerID",
        "cluster",
        "TerritoryName",
        "TotalOrders",
        "TotalSpent",
        "AvgOrderValue",
        "RecencyDays",
        "AvgDiscount"
    )

    logger.info("Writing clustered dataset (best config)...")
    final.write.mode("overwrite").parquet(OUTPUT_PATH)

    # --------------------------------------------------
    # Lưu model tốt nhất
    # --------------------------------------------------
    logger.info("Saving best model...")
    best_model.write().overwrite().save(MODEL_PATH)

    # --------------------------------------------------
    # Lưu metrics của cấu hình tốt nhất (giữ tương thích với pipeline cũ)
    # --------------------------------------------------
    logger.info("Saving best metrics JSON...")
    spark.createDataFrame(
        [(json.dumps(best),)], ["metrics_json"]
    ).write.mode("overwrite").text(METRICS_PATH)

    # --------------------------------------------------
    # Lưu toàn bộ báo cáo so sánh (để vẽ elbow chart / phân tích thêm)
    # --------------------------------------------------
    logger.info("Saving full search report (all configs tried)...")
    search_report = {
        "selection_metric": SELECTION_METRIC,
        "best_config": best,
        "all_results": all_results,
    }
    spark.createDataFrame(
        [(json.dumps(search_report),)], ["search_report_json"]
    ).write.mode("overwrite").text(SEARCH_REPORT_PATH)

    logger.info("DONE.")

    spark.stop()


# --------------------------------------------------
if __name__ == "__main__":
    main()