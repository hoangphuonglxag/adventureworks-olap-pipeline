# =============================================================================
# dags/dag_2_bronze_to_silver.py
# DAG 2/3: Làm sạch Bronze → Silver (Clean, Flatten, Normalize)
#
# Trigger: THỦ CÔNG từ Airflow UI
# =============================================================================
from __future__ import annotations
from datetime import timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago

SPARK_SUBMIT    = "/opt/spark/bin/spark-submit"
SCRIPTS_ROOT    = "/opt/spark/scripts"
SILVER_SCRIPTS  = f"{SCRIPTS_ROOT}/bronze_to_silver"

DEFAULT_ARGS = {
    "owner": "data-team",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="2_bronze_to_silver",
    description="Làm sạch Bronze → Silver: ép kiểu, xử lý NULL, flatten quan hệ",
    default_args=DEFAULT_ARGS,
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["silver", "transform", "spark"],
    doc_md="""
## DAG 2: Bronze → Silver

Đọc Parquet thô từ `s3a://bronze/` → làm sạch → ghi `s3a://silver/`.

**Các bước xử lý:**
- Ép kiểu dữ liệu chuẩn (`DECIMAL(18,4)`, `DATE`, ...)
- Xử lý NULL (`Color=N/A`, `Size=Universal`, ...)
- Deduplication
- Flatten/JOIN nội bộ (địa chỉ, khách hàng, danh mục sản phẩm)

**Script:** `scripts/bronze_to_silver/bronze_to_silver.py`
""",
) as dag:

    bronze_to_silver = BashOperator(
        task_id="bronze_to_silver",
        bash_command=(
            f"docker exec spark_master_engine "
            f"{SPARK_SUBMIT} {SILVER_SCRIPTS}/bronze_to_silver.py"
        ),
        doc_md="Chạy bronze_to_silver.py: clean + flatten toàn bộ dữ liệu.",
    )
