"""
dag_2_customer_segmentation.py

Airflow DAG: Customer Segmentation Dataset ETL

Triggers a Spark job (via spark-submit inside the spark_master_engine container)
that builds a customer-level feature dataset from AdventureWorks2022 (SQL Server OLTP)
and writes it to MinIO (s3a://silver/customer_segmentation/) as Parquet.

Downstream usage: K-Means clustering (Customer Segmentation).
"""

from datetime import timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago

DAG_ID = "dag_2_customer_segmentation"

# NOTE: this calls `docker exec` from inside the airflow-scheduler container,
# which requires:
#   1) /var/run/docker.sock mounted into airflow-scheduler (already present
#      in docker-compose.yml)
#   2) the `docker` CLI binary installed inside the apache/airflow:2.9.1 image
#      (NOT included by default — install it via a custom Dockerfile, e.g.:
#        FROM apache/airflow:2.9.1
#        USER root
#        RUN curl -fsSL https://get.docker.com | sh
#        USER airflow
#      and reference that custom image in airflow-scheduler's `build`/`image`)
SPARK_SUBMIT_CMD = (
    "docker exec spark_master_engine "
    "/opt/spark/bin/spark-submit "
    "/opt/spark/scripts/build_customer_segmentation_dataset.py"
)

default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id=DAG_ID,
    description="Build Customer Segmentation dataset from AdventureWorks2022 OLTP -> MinIO (Silver) for K-Means clustering",
    default_args=default_args,
    schedule=None,          # manual trigger only
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["spark", "etl", "customer-segmentation", "ml"],
) as dag:

    build_customer_segmentation_dataset = BashOperator(
        task_id="build_customer_segmentation_dataset",
        bash_command=SPARK_SUBMIT_CMD,
    )

    build_customer_segmentation_dataset
