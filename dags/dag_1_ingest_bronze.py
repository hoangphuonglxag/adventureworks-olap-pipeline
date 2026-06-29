# =============================================================================
# dags/dag_1_ingest_bronze.py
# DAG 1/3: Ingest SQL Server → MinIO Bronze (Parquet)
#
# Trigger: THỦ CÔNG từ Airflow UI
# =============================================================================
from __future__ import annotations
from datetime import timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago

SPARK_SUBMIT = "/opt/spark/bin/spark-submit"
SCRIPTS_ROOT = "/opt/spark/scripts"

DEFAULT_ARGS = {
    "owner": "data-team",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="1_ingest_to_bronze",
    description="Ingest 26 bảng từ SQL Server → MinIO s3a://bronze/ (Parquet Snappy)",
    default_args=DEFAULT_ARGS,
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["bronze", "ingest", "spark"],
    doc_md="""
## DAG 1: Ingest to Bronze

Cào **26 bảng thô** từ SQL Server 2022 (OLTP) → MinIO `s3a://bronze/` dạng **Parquet Snappy**.

Không transform, không clean — giữ nguyên trạng dữ liệu nguồn, chỉ thêm `_ingested_at`.

**Script:** `scripts/ingest_to_bronze.py`
""",
) as dag:

    ingest_to_bronze = BashOperator(
        task_id="ingest_to_bronze",
        bash_command=(
            f"docker exec spark_master_engine "
            f"{SPARK_SUBMIT} {SCRIPTS_ROOT}/ingest_to_bronze.py"
        ),
        doc_md="Chạy ingest_to_bronze.py: JDBC từ SQL Server → 26 Parquet files trên MinIO.",
    )
