# =============================================================================
# dags/dag_3_silver_to_gold.py
# DAG 3/3: Silver → Gold Star Schema (Dims + Facts + ML placeholder)
#
# Task graph bên trong:
#
#   ┌──────────────────────────────────────────────────────────┐
#   │  DIMENSIONS (6 tasks, chạy SONG SONG)                    │
#   │  dim_date  dim_customer  dim_product                      │
#   │  dim_geography  dim_seller  dim_vendor                    │
#   └──────────────────┬───────────────────────────────────────┘
#                      │ (tất cả Dims done → mới chạy Facts)
#   ┌──────────────────┴───────────────────────────────────────┐
#   │  FACTS (6 tasks, chạy SONG SONG)                         │
#   │  fact_order  fact_product_daily  fact_seller_daily        │
#   │  fact_order_daily  fact_inventory  fact_customer_behavior │
#   └──────────────────┬───────────────────────────────────────┘
#                      │
#              [ML - placeholder]     ← uncomment khi sẵn sàng
#                      │
#                notify_done
#
# Trigger: THỦ CÔNG từ Airflow UI
# =============================================================================
from __future__ import annotations
from datetime import timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

SPARK_SUBMIT   = "/opt/spark/bin/spark-submit"
SCRIPTS_ROOT   = "/opt/spark/scripts"
GOLD_SCRIPTS   = f"{SCRIPTS_ROOT}/silver_to_gold"

DEFAULT_ARGS = {
    "owner": "data-team",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

# ---------------------------------------------------------------------------
# Helper tạo BashOperator chạy spark-submit
# ---------------------------------------------------------------------------
def gold_task(task_id: str, script_name: str, dag: DAG) -> BashOperator:
    return BashOperator(
        task_id=task_id,
        bash_command=(
            f"docker exec spark_master_engine "
            f"{SPARK_SUBMIT} {GOLD_SCRIPTS}/{script_name}"
        ),
        dag=dag,
        doc_md=f"Chạy `{GOLD_SCRIPTS}/{script_name}` trên Spark.",
    )


with DAG(
    dag_id="3_silver_to_gold",
    description="Build Star Schema: 6 Dims song song → 6 Facts song song → PostgreSQL DW",
    default_args=DEFAULT_ARGS,
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["gold", "star-schema", "spark", "dim", "fact"],
    doc_md="""
## DAG 3: Silver → Gold (Star Schema)

Build toàn bộ **Star Schema** vào PostgreSQL `adventureworks_dw`.

### Thứ tự chạy

**Bước 1 — Dimensions (song song):**
| Task | Script | Mô tả |
|------|--------|-------|
| `dim_date` | `build_dim_date.py` | Calendar dimension (2010–2030) |
| `dim_customer` | `build_dim_customer.py` | SCD Type 2, RFM segments |
| `dim_product` | `build_dim_product.py` | SCD Type 2, giá lịch sử |
| `dim_geography` | `build_dim_geography.py` | Địa chỉ, territory |
| `dim_seller` | `build_dim_seller.py` | SCD Type 2, quota/commission |
| `dim_vendor` | `build_dim_vendor.py` | Nhà cung cấp |

**Bước 2 — Facts (song song, sau khi tất cả Dims xong):**
| Task | Script | Grain |
|------|--------|-------|
| `fact_order` | `build_fact_order.py` | 1 dòng = 1 đơn hàng |
| `fact_product_daily` | `build_fact_product_daily.py` | Ngày × Sản phẩm |
| `fact_seller_daily` | `build_fact_seller_daily.py` | Ngày × Seller |
| `fact_order_daily` | `build_fact_order_daily.py` | Tổng hợp theo ngày |
| `fact_inventory` | `build_fact_inventory.py` | Snapshot tồn kho |
| `fact_customer_behavior` | `build_fact_customer_behavior.py` | RFM + KMeans |
""",
) as dag:

    # =========================================================================
    # BƯỚC 1: DIMENSIONS — chạy song song, không phụ thuộc nhau
    # =========================================================================

    dim_date = gold_task(
        task_id="dim_date",
        script_name="build_dim_date.py",
        dag=dag,
    )

    dim_customer = gold_task(
        task_id="dim_customer",
        script_name="build_dim_customer.py",
        dag=dag,
    )

    dim_product = gold_task(
        task_id="dim_product",
        script_name="build_dim_product.py",
        dag=dag,
    )

    dim_geography = gold_task(
        task_id="dim_geography",
        script_name="build_dim_geography.py",
        dag=dag,
    )

    dim_seller = gold_task(
        task_id="dim_seller",
        script_name="build_dim_seller.py",
        dag=dag,
    )

    dim_vendor = gold_task(
        task_id="dim_vendor",
        script_name="build_dim_vendor.py",
        dag=dag,
    )

    all_dims = [dim_date, dim_customer, dim_product, dim_geography, dim_seller, dim_vendor]

    # =========================================================================
    # BƯỚC 2: FACTS — chạy song song SAU KHI tất cả Dims hoàn thành
    # Lý do: Facts cần lookup FK từ Dim tables
    # =========================================================================

    fact_order = gold_task(
        task_id="fact_order",
        script_name="build_fact_order.py",
        dag=dag,
    )

    fact_product_daily = gold_task(
        task_id="fact_product_daily",
        script_name="build_fact_product_daily.py",
        dag=dag,
    )

    fact_seller_daily = gold_task(
        task_id="fact_seller_daily",
        script_name="build_fact_seller_daily.py",
        dag=dag,
    )

    fact_order_daily = gold_task(
        task_id="fact_order_daily",
        script_name="build_fact_order_daily.py",
        dag=dag,
    )

    fact_inventory = gold_task(
        task_id="fact_inventory",
        script_name="build_fact_inventory.py",
        dag=dag,
    )

    fact_customer_behavior = gold_task(
        task_id="fact_customer_behavior",
        script_name="build_fact_customer_behavior.py",
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
    # BƯỚC 3: ML SCORING — Placeholder
    # Uncomment khi scripts ML sẵn sàng trong scripts/ml/
    # =========================================================================
    # ML_SCRIPTS = f"{SCRIPTS_ROOT}/ml"
    #
    # ml_rfm_kmeans = BashOperator(
    #     task_id="ml_rfm_kmeans",
    #     bash_command=f"docker exec spark_master_engine {SPARK_SUBMIT} {ML_SCRIPTS}/rfm_kmeans.py",
    #     dag=dag,
    # )
    # ml_product_abc = BashOperator(
    #     task_id="ml_product_abc",
    #     bash_command=f"docker exec spark_master_engine {SPARK_SUBMIT} {ML_SCRIPTS}/product_abc_class.py",
    #     dag=dag,
    # )
    # all_ml = [ml_rfm_kmeans, ml_product_abc]

    # =========================================================================
    # NOTIFY DONE
    # =========================================================================
    def summary(**context):
        print("=" * 60)
        print("  ✅  GOLD LAYER LOAD HOÀN THÀNH")
        print(f"  Run: {context['run_id']}")
        print("  Dims: dim_date, dim_customer, dim_product,")
        print("        dim_geography, dim_seller, dim_vendor")
        print("  Facts: fact_order, fact_product_daily,")
        print("         fact_seller_daily, fact_order_daily,")
        print("         fact_inventory, fact_customer_behavior")
        print("  Dashboard: http://localhost:8501")
        print("=" * 60)

    notify_done = PythonOperator(
        task_id="notify_done",
        python_callable=summary,
        dag=dag,
    )

    # =========================================================================
    # DEPENDENCY GRAPH
    # Dims chạy song song → tất cả dims xong → Facts chạy song song → done
    #
    # Khi thêm ML:
    #   thay: all_facts >> notify_done
    #   bằng: all_facts >> all_ml >> notify_done
    # =========================================================================
    for dim in all_dims:
        dim >> all_facts          # mỗi dim → tất cả facts (fan-out)

    for fact in all_facts:
        fact >> notify_done       # mỗi fact → notify (fan-in)
