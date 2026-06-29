# =============================================================================
# dags/adventureworks_pipeline.py
# DAG: AdventureWorks OLAP Pipeline
#
# Cấu trúc task graph:
#
#   ingest_bronze
#        │
#   bronze_to_silver
#        │
#   ┌────┴──────────────────────────────────────────────────┐
#   dim_date  dim_customer  dim_product  dim_geography  dim_seller  dim_vendor
#   └────┬──────────────────────────────────────────────────┘
#        │  (tất cả Dims xong mới chạy Facts)
#   ┌────┴────────────────────────────────────────────────────────────────┐
#   fact_order  fact_product_daily  fact_seller_daily  fact_order_daily  ...
#   └────┬────────────────────────────────────────────────────────────────┘
#        │
#   [ml_scoring]   ← placeholder, uncomment khi script ML sẵn sàng
#        │
#   notify_done
#
# Trigger: THỦ CÔNG qua Airflow UI (schedule=None)
# =============================================================================

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SPARK_SUBMIT = "/opt/spark/bin/spark-submit"
SPARK_MASTER = "spark://spark-master-engine:7077"

# Đường dẫn scripts (mount vào spark_master_engine qua volume ./scripts)
SCRIPTS_ROOT   = "/opt/spark/scripts"
SILVER_TO_GOLD = f"{SCRIPTS_ROOT}/silver_to_gold"
BRONZE_TO_SILVER = f"{SCRIPTS_ROOT}/bronze_to_silver"

# ---------------------------------------------------------------------------
# Default args
# ---------------------------------------------------------------------------
DEFAULT_ARGS = {
    "owner": "data-team",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
    "email_on_retry": False,
}

# ---------------------------------------------------------------------------
# Helper: tạo BashOperator chạy spark-submit trong container spark_master_engine
# ---------------------------------------------------------------------------
def spark_task(task_id: str, script_path: str, dag: DAG) -> BashOperator:
    """
    Chạy spark-submit script bên trong container spark_master_engine.
    Dùng `docker exec` từ Airflow scheduler → gọi script trong Spark cluster.
    """
    return BashOperator(
        task_id=task_id,
        bash_command=(
            f"docker exec spark_master_engine "
            f"{SPARK_SUBMIT} {script_path}"
        ),
        dag=dag,
        doc_md=f"Chạy `{script_path}` trên Spark cluster.",
    )


# ---------------------------------------------------------------------------
# DAG Definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="adventureworks_olap_pipeline",
    description=(
        "Medallion pipeline: SQL Server → Bronze (MinIO) → Silver → Gold (PostgreSQL). "
        "Dims load song song, sau đó Facts load song song."
    ),
    default_args=DEFAULT_ARGS,
    schedule=None,          # CHỈ trigger thủ công từ UI
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,      # Không chạy song song 2 pipeline cùng lúc
    tags=["adventureworks", "spark", "etl", "medallion"],
    doc_md="""
## AdventureWorks OLAP Pipeline

**Kiến trúc Medallion (3 tầng):**

| Tầng | Mô tả | Lưu trữ |
|------|-------|---------|
| 🥉 Bronze | Raw data từ SQL Server | MinIO `s3a://bronze/` |
| 🥈 Silver | Cleaned & flattened | MinIO `s3a://silver/` |
| 🥇 Gold | Star Schema (Dim + Fact) | PostgreSQL `adventureworks_dw` |

**Cách trigger thủ công:**
1. Vào DAG `adventureworks_olap_pipeline`
2. Bấm nút ▶ (Trigger DAG) góc phải trên
3. Theo dõi Graph View để xem tiến trình từng task

**Dashboard:** [http://localhost:8501](http://localhost:8501)
""",
) as dag:

    # =========================================================================
    # TẦNG 1: BRONZE — Ingest từ SQL Server vào MinIO
    # =========================================================================
    ingest_bronze = spark_task(
        task_id="ingest_to_bronze",
        script_path=f"{SCRIPTS_ROOT}/ingest_to_bronze.py",
        dag=dag,
    )

    # =========================================================================
    # TẦNG 2: SILVER — Làm sạch & flatten dữ liệu
    # =========================================================================
    bronze_to_silver = spark_task(
        task_id="bronze_to_silver",
        script_path=f"{BRONZE_TO_SILVER}/bronze_to_silver.py",
        dag=dag,
    )

    # =========================================================================
    # TẦNG 3: GOLD — DIMENSIONS (chạy song song, độc lập nhau)
    # Phải hoàn thành tất cả Dims trước khi Facts có thể lookup FK
    # =========================================================================

    dim_date = spark_task(
        task_id="gold_dim_date",
        script_path=f"{SILVER_TO_GOLD}/build_dim_date.py",
        dag=dag,
    )

    dim_customer = spark_task(
        task_id="gold_dim_customer",
        script_path=f"{SILVER_TO_GOLD}/build_dim_customer.py",
        dag=dag,
    )

    dim_product = spark_task(
        task_id="gold_dim_product",
        script_path=f"{SILVER_TO_GOLD}/build_dim_product.py",
        dag=dag,
    )

    dim_geography = spark_task(
        task_id="gold_dim_geography",
        script_path=f"{SILVER_TO_GOLD}/build_dim_geography.py",
        dag=dag,
    )

    dim_seller = spark_task(
        task_id="gold_dim_seller",
        script_path=f"{SILVER_TO_GOLD}/build_dim_seller.py",
        dag=dag,
    )

    dim_vendor = spark_task(
        task_id="gold_dim_vendor",
        script_path=f"{SILVER_TO_GOLD}/build_dim_vendor.py",
        dag=dag,
    )

    # Group tất cả dims để dễ set dependency với facts
    all_dims = [dim_date, dim_customer, dim_product, dim_geography, dim_seller, dim_vendor]

    # =========================================================================
    # TẦNG 3: GOLD — FACTS (chạy song song SAU KHI tất cả Dims xong)
    # Mỗi Fact cần lookup FK từ các Dim tương ứng
    # =========================================================================

    fact_order = spark_task(
        task_id="gold_fact_order",
        script_path=f"{SILVER_TO_GOLD}/build_fact_order.py",
        dag=dag,
    )

    fact_product_daily = spark_task(
        task_id="gold_fact_product_daily",
        script_path=f"{SILVER_TO_GOLD}/build_fact_product_daily.py",
        dag=dag,
    )

    fact_seller_daily = spark_task(
        task_id="gold_fact_seller_daily",
        script_path=f"{SILVER_TO_GOLD}/build_fact_seller_daily.py",
        dag=dag,
    )

    fact_order_daily = spark_task(
        task_id="gold_fact_order_daily",
        script_path=f"{SILVER_TO_GOLD}/build_fact_order_daily.py",
        dag=dag,
    )

    fact_inventory = spark_task(
        task_id="gold_fact_inventory",
        script_path=f"{SILVER_TO_GOLD}/build_fact_inventory.py",
        dag=dag,
    )

    fact_customer_behavior = spark_task(
        task_id="gold_fact_customer_behavior",
        script_path=f"{SILVER_TO_GOLD}/build_fact_customer_behavior.py",
        dag=dag,
    )

    all_facts = [
        fact_order,
        fact_product_daily,
        fact_seller_daily,
        fact_order_daily,
        fact_inventory,
        fact_customer_behavior,
    ]

    # =========================================================================
    # TẦNG 4: ML SCORING — Placeholder (uncomment khi scripts ML sẵn sàng)
    # =========================================================================
    # ml_rfm_kmeans = spark_task(
    #     task_id="ml_rfm_kmeans",
    #     script_path=f"{SCRIPTS_ROOT}/ml/rfm_kmeans.py",
    #     dag=dag,
    # )
    # ml_product_abc = spark_task(
    #     task_id="ml_product_abc",
    #     script_path=f"{SCRIPTS_ROOT}/ml/product_abc_class.py",
    #     dag=dag,
    # )
    # all_ml = [ml_rfm_kmeans, ml_product_abc]

    # =========================================================================
    # NOTIFY DONE
    # =========================================================================
    def pipeline_summary(**context):
        run_id     = context["run_id"]
        logical_dt = context["logical_date"]
        print("=" * 65)
        print("  ✅  ADVENTUREWORKS PIPELINE HOÀN THÀNH")
        print(f"  Run ID      : {run_id}")
        print(f"  Logical Date: {logical_dt}")
        print("=" * 65)
        print("  Gold Layer (PostgreSQL adventureworks_dw):")
        print("    Dims : dim_date, dim_customer, dim_product,")
        print("           dim_geography, dim_seller, dim_vendor")
        print("    Facts: fact_order, fact_product_daily,")
        print("           fact_seller_daily, fact_order_daily,")
        print("           fact_inventory, fact_customer_behavior")
        print("  Dashboard: http://localhost:8501")
        print("=" * 65)

    notify_done = PythonOperator(
        task_id="notify_done",
        python_callable=pipeline_summary,
        dag=dag,
        doc_md="Log tổng kết sau khi pipeline hoàn thành.",
    )

    # =========================================================================
    # DEPENDENCY GRAPH
    # =========================================================================
    #
    #   ingest_bronze
    #        │
    #   bronze_to_silver
    #        │
    #   ┌────┴─────────────────────────────────────┐
    #   dim_date  dim_customer  dim_product  ...   dim_vendor
    #   └────┬─────────────────────────────────────┘
    #        │
    #   ┌────┴──────────────────────────────────────────┐
    #   fact_order  fact_product_daily  ...  fact_customer_behavior
    #   └────┬──────────────────────────────────────────┘
    #        │
    #   notify_done
    #
    # Uncomment khi thêm ML:
    # └────┬──────────────────┐
    #   ml_rfm_kmeans   ml_product_abc
    #   └────┬──────────────────┘
    #        │
    #   notify_done
    # =========================================================================

    # Bronze → Silver (tuyến tính, phải theo thứ tự)
    ingest_bronze >> bronze_to_silver

    # Silver → tất cả Dims song song
    bronze_to_silver >> all_dims

    # Tất cả Dims xong → tất cả Facts song song
    for dim in all_dims:
        dim >> all_facts

    # Tất cả Facts xong → notify
    # (Uncomment dòng dưới và comment dòng cuối khi thêm ML)
    # for fact in all_facts:
    #     fact >> all_ml
    # for ml in all_ml:
    #     ml >> notify_done

    for fact in all_facts:
        fact >> notify_done
