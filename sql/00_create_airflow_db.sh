#!/bin/bash
# =============================================================================
# 00_create_airflow_db.sh
# Chạy TỰ ĐỘNG khi Postgres container khởi tạo lần đầu
# (đặt trong /docker-entrypoint-initdb.d/ → chạy TRƯỚC init.sql vì tên "00_")
#
# Mục đích: Tạo database "airflow_meta" cho Airflow metadata
# Database mặc định "gold_dw" đã được Postgres tự tạo qua POSTGRES_DB env var
# =============================================================================

set -e

echo "=== Creating airflow_meta database ==="
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE airflow_meta'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow_meta')\gexec
EOSQL
echo "=== airflow_meta database ready ==="