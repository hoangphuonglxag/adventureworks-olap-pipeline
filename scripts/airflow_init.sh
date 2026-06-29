#!/bin/bash
# =============================================================================
# scripts/airflow_init.sh
# Chạy bên trong container airflow-init:
#   1. Chờ PostgreSQL sẵn sàng
#   2. Tạo database airflow_meta (nếu chưa có)
#   3. Migrate Airflow schema
#   4. Tạo user admin
# =============================================================================

set -e

echo "=== [Airflow Init] Waiting for PostgreSQL to be ready... ==="
for i in $(seq 1 30); do
    python -c "
import psycopg2, sys, os
try:
    conn = psycopg2.connect(
        host='postgres-gold', port=5432,
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'],
        dbname='postgres'
    )
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f'Attempt $i/30: {e}')
    sys.exit(1)
" && break || sleep 3
done

echo "=== [Airflow Init] Creating airflow_meta database if not exists... ==="
python -c "
import psycopg2, os
conn = psycopg2.connect(
    host='postgres-gold', port=5432,
    user=os.environ['POSTGRES_USER'],
    password=os.environ['POSTGRES_PASSWORD'],
    dbname='postgres'
)
conn.autocommit = True
cur = conn.cursor()
cur.execute(\"SELECT 1 FROM pg_database WHERE datname='airflow_meta'\")
if not cur.fetchone():
    cur.execute('CREATE DATABASE airflow_meta')
    print('[OK] Created airflow_meta database')
else:
    print('[OK] airflow_meta already exists')
conn.close()
"

echo "=== [Airflow Init] Running db migrate... ==="
airflow db migrate

echo "=== [Airflow Init] Creating admin user... ==="
airflow users create \
    --username admin \
    --password admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@admin.com || echo "[SKIP] User already exists"

echo "=== [Airflow Init] DONE! ==="
