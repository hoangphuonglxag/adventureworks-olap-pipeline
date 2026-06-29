# =============================================================================
# gold_utils.py
# Shared utilities for Silver → Gold layer
# AdventureWorks2022
#
# Chứa:
#   - PG config (đọc từ env)
#   - execute_sql()      : chạy DML/DDL trực tiếp qua Py4J JDBC
#   - read_silver()      : đọc Parquet từ MinIO Silver bucket
#   - read_pg_table()    : đọc bảng từ Postgres Gold
#   - upsert_to_gold()   : UPSERT qua staging table (dùng cho SCD1 / Fact)
#   - scd2_merge()       : SCD Type 2 merge (dùng cho dim_seller, dim_customer)
#   - get_watermark()    : đọc watermark incremental
#   - update_watermark() : cập nhật watermark sau load
# =============================================================================

import os
from datetime import date, datetime, timezone
from functools import reduce

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

# --------------------------------------------------------------------------- #
# CONFIG                                                                        #
# --------------------------------------------------------------------------- #

PG_URL      = os.environ.get("POSTGRES_GOLD_URL",      "jdbc:postgresql://postgres_gold_dw:5432/gold_dw")
PG_USER     = os.environ.get("POSTGRES_GOLD_USER",     "gold_user")
PG_PASSWORD = os.environ.get("POSTGRES_GOLD_PASSWORD", "adminpassword")
PG_DRIVER   = "org.postgresql.Driver"

MINIO_BUCKET_SILVER = "silver"

# Sentinel key cho member không tìm được trong dimension (thay cho -1)
UNKNOWN_KEY = "UNKNOWN"

# Watermark mặc định = load toàn bộ lịch sử
DEFAULT_WATERMARK = datetime(2000, 1, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# INTERNAL: JDBC CONNECTION                                                     #
# --------------------------------------------------------------------------- #

def _jdbc_conn(spark: SparkSession):
    """Tạo Java JDBC connection tới Postgres qua Py4J (không cần psycopg2)."""
    return spark._jvm.java.sql.DriverManager.getConnection(PG_URL, PG_USER, PG_PASSWORD)


# --------------------------------------------------------------------------- #
# PUBLIC: SQL EXECUTION                                                         #
# --------------------------------------------------------------------------- #

def execute_sql(spark: SparkSession, sql: str) -> None:
    """Thực thi DML / DDL trực tiếp trên PostgreSQL qua Py4J."""
    conn = None
    try:
        conn = _jdbc_conn(spark)
        conn.setAutoCommit(True)
        conn.createStatement().execute(sql)
    finally:
        if conn:
            conn.close()


# --------------------------------------------------------------------------- #
# PUBLIC: READ HELPERS                                                          #
# --------------------------------------------------------------------------- #

def read_silver(spark: SparkSession, table: str) -> DataFrame:
    """Đọc Parquet từ Silver bucket trên MinIO."""
    return spark.read.parquet(f"s3a://{MINIO_BUCKET_SILVER}/{table}")


def read_pg_table(spark: SparkSession, table_or_query: str) -> DataFrame:
    """Đọc bảng (hoặc subquery) từ PostgreSQL Gold."""
    return (
        spark.read.format("jdbc")
        .option("url",      PG_URL)
        .option("dbtable",  table_or_query)
        .option("user",     PG_USER)
        .option("password", PG_PASSWORD)
        .option("driver",   PG_DRIVER)
        .load()
    )


# --------------------------------------------------------------------------- #
# PUBLIC: UPSERT (SCD Type 1 / Fact tables)                                   #
# --------------------------------------------------------------------------- #

def upsert_to_gold(spark: SparkSession, df: DataFrame, table_name: str, pk_col: str) -> int:
    """
    UPSERT vào bảng Gold theo cơ chế 3 bước:
      1. Ghi df vào bảng staging (Spark JDBC overwrite)
      2. INSERT INTO <target> ... ON CONFLICT DO UPDATE
      3. DROP TABLE staging

    Phù hợp cho: dim_date, dim_product, dim_geography, dim_vendor, fact_*

    Returns:
        Số dòng đã upsert
    """
    staging  = f"{table_name}_stg"
    cols     = df.columns
    non_pk   = [c for c in cols if c != pk_col]
    col_list = ", ".join([f'"{c}"' for c in cols])
    update_set = ", ".join([f'"{c}" = EXCLUDED."{c}"' for c in non_pk])

    # Bước 1: staging
    (
        df.write.format("jdbc")
        .option("url",      PG_URL)
        .option("dbtable",  staging)
        .option("user",     PG_USER)
        .option("password", PG_PASSWORD)
        .option("driver",   PG_DRIVER)
        .mode("overwrite")
        .save()
    )

    # Bước 2: upsert
    execute_sql(spark, f"""
        INSERT INTO {table_name} ({col_list})
        SELECT {col_list} FROM {staging}
        ON CONFLICT ("{pk_col}") DO UPDATE SET {update_set};
    """)

    # Bước 3: cleanup
    execute_sql(spark, f"DROP TABLE IF EXISTS {staging};")

    count = df.count()
    return count


# --------------------------------------------------------------------------- #
# PUBLIC: SCD TYPE 2 MERGE                                                     #
# --------------------------------------------------------------------------- #

def scd2_merge(
    spark: SparkSession,
    new_df: DataFrame,
    table_name: str,
    biz_key_col: str,
    sk_col: str,
    tracked_cols: list,
) -> int:
    """
    SCD Type 2 Merge — lưu lịch sử thay đổi của dimension.

    Logic:
      ┌─────────────────────────────────────────────────────────────┐
      │ New record (chưa có trong Gold)   → INSERT với is_current=T │
      │ Changed record (hash khác)        → EXPIRE old + INSERT new │
      │ Unchanged record                  → bỏ qua (no-op)          │
      └─────────────────────────────────────────────────────────────┘

    Cột bắt buộc trong new_df:
      - <biz_key_col>   : business key (vd: customer_id, seller_id)
      - <sk_col>        : surrogate key (sha2 của biz_key || date)
      - effective_date  : ngày bắt đầu hiệu lực
      - expiry_date     : NULL (sẽ set khi expire)
      - is_current      : TRUE
      - version         : SMALLINT

    Args:
        spark         : SparkSession
        new_df        : DataFrame mới từ Silver (đã gọi build_dim_*())
        table_name    : Tên bảng Gold (vd: 'dim_seller')
        biz_key_col   : Cột business key (vd: 'seller_id')
        sk_col        : Tên cột surrogate key (vd: 'seller_key')
        tracked_cols  : Các cột cần theo dõi thay đổi

    Returns:
        Số dòng đã INSERT (new + new-version-of-changed)
    """
    today = str(date.today())

    # ── 1. Thử đọc active records từ Postgres ────────────────────────────── #
    try:
        current_df = read_pg_table(
            spark,
            f"(SELECT * FROM {table_name} WHERE is_current = TRUE) AS _cur"
        )
        has_data = current_df.count() > 0
    except Exception:
        has_data = False

    if not has_data:
        # First load — insert toàn bộ
        row_count = new_df.count()
        print(f"    [SCD2] First load → INSERT {row_count:,} dòng vào '{table_name}'")
        (
            new_df.write.format("jdbc")
            .option("url",      PG_URL)
            .option("dbtable",  table_name)
            .option("user",     PG_USER)
            .option("password", PG_PASSWORD)
            .option("driver",   PG_DRIVER)
            .mode("append")
            .save()
        )
        return row_count

    # ── 2. Tính hash của tracked_cols để phát hiện thay đổi ─────────────── #
    hash_expr = F.sha2(
        F.concat_ws("||", *[
            F.coalesce(F.col(c).cast("string"), F.lit("")) for c in tracked_cols
        ]),
        256
    )

    cur_hashed = current_df.withColumn("_hash", hash_expr).select(
        F.col(biz_key_col).alias("_cur_biz"),
        F.col("_hash").alias("_cur_hash"),
        F.col("version").alias("_cur_ver")
    )
    new_hashed = new_df.withColumn("_hash", hash_expr)

    # ── 3. Join phát hiện changed / new ─────────────────────────────────── #
    joined = (
        new_hashed.alias("n")
        .join(cur_hashed.alias("c"),
              F.col(f"n.{biz_key_col}") == F.col("c._cur_biz"),
              "left_outer")
    )

    changed_ids = [
        row[biz_key_col]
        for row in joined.filter(
            F.col("c._cur_biz").isNotNull() &
            (F.col("n._hash") != F.col("c._cur_hash"))
        ).select(biz_key_col).collect()
    ]

    new_records_df = joined.filter(F.col("c._cur_biz").isNull())

    # ── 4. Expire bản cũ của những record đã thay đổi ───────────────────── #
    if changed_ids:
        ids_str = ", ".join([str(i) for i in changed_ids])
        execute_sql(spark, f"""
            UPDATE {table_name}
            SET    is_current  = FALSE,
                   expiry_date = '{today}'
            WHERE  {biz_key_col} IN ({ids_str})
            AND    is_current  = TRUE;
        """)
        print(f"    [SCD2] Expired {len(changed_ids)} record(s) trong '{table_name}'")

    # ── 5. Chuẩn bị INSERT: new + changed (version++) ────────────────────── #
    def prepare_insert(source: DataFrame, version_offset_col: str) -> DataFrame:
        """Cập nhật metadata SCD2 và tạo surrogate key mới cho version mới."""
        return (
            source
            .withColumn("effective_date", F.lit(today).cast("date"))
            .withColumn("expiry_date",    F.lit(None).cast("date"))
            .withColumn("is_current",     F.lit(True))
            .withColumn("version",
                F.when(F.col(version_offset_col).isNotNull(),
                       (F.col(version_offset_col) + 1).cast("short"))
                .otherwise(F.lit(1).cast("short"))
            )
            # Surrogate key mới = sha2(biz_key || today)
            .withColumn(sk_col,
                F.sha2(F.concat_ws("||",
                    F.col(biz_key_col).cast("string"), F.lit(today)), 256)
            )
            .drop("_hash", "_cur_biz", "_cur_hash", "_cur_ver")
        )

    to_insert_parts = []

    if changed_ids:
        changed_df = joined.filter(F.col(biz_key_col).isin(changed_ids))
        to_insert_parts.append(prepare_insert(changed_df, "_cur_ver"))

    if new_records_df.count() > 0:
        to_insert_parts.append(
            new_records_df.drop("_hash", "_cur_biz", "_cur_hash", "_cur_ver")
        )

    if not to_insert_parts:
        print(f"    [SCD2] Không có thay đổi nào trong '{table_name}' — skip.")
        return 0

    final_df = reduce(DataFrame.union, to_insert_parts)
    insert_count = final_df.count()

    (
        final_df.write.format("jdbc")
        .option("url",      PG_URL)
        .option("dbtable",  table_name)
        .option("user",     PG_USER)
        .option("password", PG_PASSWORD)
        .option("driver",   PG_DRIVER)
        .mode("append")
        .save()
    )

    print(f"    [SCD2] Inserted {insert_count} dòng → '{table_name}' "
          f"({len(changed_ids)} changed + {insert_count - len(changed_ids)} new)")
    return insert_count


# --------------------------------------------------------------------------- #
# PUBLIC: WATERMARK (Incremental Load)                                         #
# --------------------------------------------------------------------------- #

def get_watermark(spark: SparkSession, table_name: str) -> datetime:
    """
    Đọc mốc load cuối từ pipeline_watermark.
    Trả về DEFAULT_WATERMARK (2000-01-01) nếu chưa có record.
    """
    try:
        df = read_pg_table(
            spark,
            f"(SELECT last_loaded FROM pipeline_watermark WHERE table_name = '{table_name}') AS tmp"
        )
        row = df.first()
        if row and row["last_loaded"]:
            dt = row["last_loaded"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        return DEFAULT_WATERMARK
    except Exception as e:
        print(f"  [WATERMARK] Không đọc được '{table_name}': {e}")
        return DEFAULT_WATERMARK


def update_watermark(spark: SparkSession, table_name: str,
                     new_ts: datetime, row_count: int = 0) -> None:
    """Cập nhật pipeline_watermark sau khi load thành công."""
    conn = None
    try:
        ts_str = new_ts.strftime("%Y-%m-%d %H:%M:%S")
        conn = _jdbc_conn(spark)
        conn.setAutoCommit(True)
        conn.createStatement().execute(f"""
            INSERT INTO pipeline_watermark (table_name, last_loaded, row_count)
            VALUES ('{table_name}', '{ts_str}', {row_count})
            ON CONFLICT (table_name) DO UPDATE
                SET last_loaded = EXCLUDED.last_loaded,
                    row_count   = EXCLUDED.row_count,
                    updated_at  = CURRENT_TIMESTAMP;
        """)
        print(f"  [WATERMARK] '{table_name}' → {ts_str}  ({row_count:,} rows)")
    except Exception as e:
        print(f"  [WATERMARK] Lỗi update '{table_name}': {e}")
    finally:
        if conn:
            conn.close()


def get_watermark_date_str(spark: SparkSession, table_name: str) -> str:
    """Trả về watermark dạng 'YYYY-MM-DD' để dùng trực tiếp trong filter."""
    return get_watermark(spark, table_name).strftime("%Y-%m-%d")
