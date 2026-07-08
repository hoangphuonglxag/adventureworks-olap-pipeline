"""
dag_3_customer_kmeans.py

Airflow DAG: Customer Segmentation - KMeans Clustering

Input :
    s3a://silver/customer_segmentation/   (from ETL job)

Process:
    Spark ML KMeans clustering

Output:
    s3a://gold/customer_segments/ (clustered customers)
"""

from datetime import timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago

DAG_ID = "dag_3_customer_kmeans"

SPARK_SUBMIT_CMD = (
    "docker exec spark_master_engine "
    "/opt/spark/bin/spark-submit "
    "/opt/spark/scripts/run_customer_kmeans.py"
)

default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id=DAG_ID,
    description="Run KMeans clustering for customer segmentation",
    default_args=default_args,
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["spark", "ml", "kmeans", "customer-segmentation"],
) as dag:

    run_kmeans = BashOperator(
        task_id="run_customer_kmeans",
        bash_command=SPARK_SUBMIT_CMD,
    )

    run_kmeans