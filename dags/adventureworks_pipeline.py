# =============================================================================
# dags/adventureworks_pipeline.py
# DAG: AdventureWorks OLAP Pipeline  (Bronze → Silver → Gold)
#
# Trigger: THỦ CÔNG qua Airflow UI (schedule=None)
# Executor: LocalExecutor  |  Spark: DockerOperator → spark_master_engine
# =============================================================================

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.docker_operator import DockerOperator
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from docker.types import Mount

# ---------------------------------------------------------------------------
# Default args áp dụng cho tất cả tasks
# ---------------------------------------------------------------------------
DEFAULT_ARGS = {
    "owner": "data-team",
    "depends_on_past": False,           # Task không phụ thuộc lần chạy trước
    "retries": 1,                        # Tự retry 1 lần nếu fail
    "retry_delay": timedelta(minutes=5), # Chờ 5 phút trước khi retry
    "email_on_failure": False,
    "email_on_retry": False,
}

# ---------------------------------------------------------------------------
# Spark submit command builder — tái sử dụng cho cả 3 tầng
# ---------------------------------------------------------------------------
SPARK_MASTER = "spark://spark-master-engine:7077"
SPARK_BIN    = "/opt/spark/bin/spark-submit"
SCRIPTS_DIR  = "/opt/spark/scripts"

def spark_cmd(script_name: str) -> str:
    """Trả về lệnh spark-submit hoàn chỉnh cho script tương ứng."""
    return f"{SPARK_BIN} {SCRIPTS_DIR}/{script_name}"


# ---------------------------------------------------------------------------
# Callback functions — log kết quả sau mỗi task
# ---------------------------------------------------------------------------
def on_success_callback(context):
    task_id  = context["task_instance"].task_id
    run_id   = context["run_id"]
    duration = context["task_instance"].duration
    print(f"[✅ SUCCESS] Task '{task_id}' | Run: {run_id} | Duration: {duration:.1f}s")


def on_failure_callback(context):
    task_id  = context["task_instance"].task_id
    run_id   = context["run_id"]
    exception = context.get("exception", "Unknown error")
    print(f"[❌ FAILED] Task '{task_id}' | Run: {run_id} | Error: {exception}")


# ---------------------------------------------------------------------------
# DAG Definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="adventureworks_olap_pipeline",
    description="End-to-end pipeline: SQL Server → Bronze (MinIO) → Silver → Gold (PostgreSQL)",
    default_args=DEFAULT_ARGS,

    # ── QUAN TRỌNG: schedule=None → chỉ trigger THỦ CÔNG từ UI ──
    schedule=None,

    start_date=days_ago(1),
    catchup=False,          # Không chạy bù các khoảng thời gian đã qua
    max_active_runs=1,      # Chỉ 1 pipeline chạy tại 1 thời điểm (tránh race condition)

    tags=["adventureworks", "spark", "etl", "olap"],

    # Doc hiển thị trong Airflow UI
    doc_md="""
## AdventureWorks OLAP Pipeline

Pipeline 3 tầng theo kiến trúc **Medallion Architecture**:

| Tầng | Script | Nguồn → Đích |
|------|--------|-------------|
| 🥉 Bronze | `ingest_to_bronze.py` | SQL Server 2022 → MinIO (Parquet) |
| 🥈 Silver | `bronze_to_silver.py` | MinIO Bronze → MinIO Silver (cleaned) |
| 🥇 Gold   | `silver_to_gold.py`   | MinIO Silver → PostgreSQL DW (Star Schema) |

**Cách trigger:** Vào DAG → nút ▶ (Trigger DAG) ở góc phải trên.

**Xem kết quả:** Dashboard Streamlit tại [http://localhost:8501](http://localhost:8501)
    """,
) as dag:

    # -----------------------------------------------------------------------
    # Task 1: Ingest to Bronze
    # SQL Server (OLTP) → MinIO s3a://bronze/ (26 bảng Parquet Snappy)
    # -----------------------------------------------------------------------
    ingest_bronze = DockerOperator(
        task_id="ingest_to_bronze",
        image="apache/spark:3.5.0",
        container_name="task_ingest_bronze",
        command=spark_cmd("ingest_to_bronze.py"),
        network_mode="adventureworks-olap-pipeline_retail_network",
        auto_remove=True,           # Xóa container tạm sau khi xong
        docker_url="unix://var/run/docker.sock",
        environment={
            "SPARK_MASTER": SPARK_MASTER,
        },
        mounts=[
            Mount(
                source="/opt/spark/scripts",   # Mount scripts từ host
                target="/opt/spark/scripts",
                type="bind",
            ),
        ],
        on_success_callback=on_success_callback,
        on_failure_callback=on_failure_callback,
        doc_md="**Bronze Layer**: Cào 26 bảng từ SQL Server → MinIO Parquet.",
    )

    # -----------------------------------------------------------------------
    # Task 2: Bronze → Silver (Cleansing & Flattening)
    # -----------------------------------------------------------------------
    transform_silver = DockerOperator(
        task_id="transform_to_silver",
        image="apache/spark:3.5.0",
        container_name="task_transform_silver",
        command=spark_cmd("bronze_to_silver.py"),
        network_mode="adventureworks-olap-pipeline_retail_network",
        auto_remove=True,
        docker_url="unix://var/run/docker.sock",
        on_success_callback=on_success_callback,
        on_failure_callback=on_failure_callback,
        doc_md="**Silver Layer**: Làm sạch dữ liệu, xử lý NULL, flatten quan hệ.",
    )

    # -----------------------------------------------------------------------
    # Task 3: Silver → Gold (Star Schema + ML)
    # -----------------------------------------------------------------------
    load_gold = DockerOperator(
        task_id="load_to_gold",
        image="apache/spark:3.5.0",
        container_name="task_load_gold",
        command=spark_cmd("silver_to_gold.py"),
        network_mode="adventureworks-olap-pipeline_retail_network",
        auto_remove=True,
        docker_url="unix://var/run/docker.sock",
        on_success_callback=on_success_callback,
        on_failure_callback=on_failure_callback,
        doc_md="**Gold Layer**: Build Dim/Fact tables + KMeans RFM → PostgreSQL DW.",
    )

    # -----------------------------------------------------------------------
    # Task 4: Pipeline Done — ghi log tổng kết
    # -----------------------------------------------------------------------
    def pipeline_summary(**context):
        run_id      = context["run_id"]
        logical_dt  = context["logical_date"]
        print("=" * 60)
        print(f"  ✅ PIPELINE HOÀN THÀNH")
        print(f"  Run ID      : {run_id}")
        print(f"  Logical Date: {logical_dt}")
        print(f"  Dashboard   : http://localhost:8501")
        print("=" * 60)
        print("  Dữ liệu mới nhất đã sẵn sàng trên Dashboard!")
        print("  → Bronze: MinIO s3a://bronze/")
        print("  → Silver: MinIO s3a://silver/")
        print("  → Gold  : PostgreSQL adventureworks_dw")
        print("=" * 60)

    notify_done = PythonOperator(
        task_id="notify_pipeline_done",
        python_callable=pipeline_summary,
        doc_md="Ghi log tổng kết sau khi toàn bộ pipeline hoàn thành.",
    )

    # -----------------------------------------------------------------------
    # Dependency graph: tuyến tính theo thứ tự Medallion
    # Bronze → Silver → Gold → Done
    # -----------------------------------------------------------------------
    ingest_bronze >> transform_silver >> load_gold >> notify_done
