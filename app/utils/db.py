"""
db.py — Kết nối & truy vấn PostgreSQL Data Warehouse (gold_dw)
Dùng chung cho toàn bộ app Streamlit (Home.py + pages/*.py)
"""
import os
from typing import Optional

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


@st.cache_resource(show_spinner=False)
def get_engine():
    """
    Tạo SQLAlchemy engine kết nối đến PostgreSQL Data Warehouse.
    @st.cache_resource giúp tái sử dụng connection pool giữa các lượt tải trang/rerun.
    """
    user = os.getenv("POSTGRES_USER", "gold_user")
    password = os.getenv("POSTGRES_PASSWORD", "adminpassword")
    db = os.getenv("POSTGRES_DB", "gold_dw")
    # Trong Docker: host là tên service (vd: postgres-gold). Chạy local: đổi thành localhost.
    host = os.getenv("POSTGRES_HOST", "postgres-gold")
    port = os.getenv("POSTGRES_PORT", "5432")
    url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)


@st.cache_data(ttl=600, show_spinner="Đang truy vấn dữ liệu...")
def run_query(query: str, params: Optional[dict] = None) -> pd.DataFrame:
    """
    Thực thi câu SQL (hỗ trợ tham số dạng :name) và trả về DataFrame.
    Cache 10 phút để giảm tải cho DB — bấm nút "Làm mới dữ liệu" ở sidebar để xoá cache.
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params=params or {})
    return df


@st.cache_data(ttl=600, show_spinner=False)
def get_date_bounds():
    """Lấy ngày nhỏ nhất / lớn nhất có phát sinh đơn hàng — dùng làm mặc định cho bộ lọc ngày."""
    q = """
        SELECT MIN(d.full_date) AS min_date, MAX(d.full_date) AS max_date
        FROM dim_date d
        JOIN fact_order_daily f ON f.date_key = d.date_key
    """
    df = run_query(q)
    if df.empty or pd.isna(df.loc[0, "min_date"]):
        return None, None
    return df.loc[0, "min_date"], df.loc[0, "max_date"]


def clear_cache():
    st.cache_data.clear()
    st.toast("Đã xoá cache — dữ liệu sẽ được truy vấn lại.", icon="🔄")


def fmt_num(value, decimals: int = 0, suffix: str = "") -> str:
    """Format số dạng 1,234,567"""
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f}{suffix}"


def fmt_pct(value, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f}%"


def safe_div(a, b):
    try:
        if b in (0, None) or pd.isna(b):
            return None
        return a / b
    except (TypeError, ZeroDivisionError):
        return None


def db_connection_guard():
    """
    Kiểm tra kết nối DB sớm; nếu lỗi thì hiện thông báo thân thiện và dừng trang.
    Gọi đầu mỗi page: `from utils.db import db_connection_guard; db_connection_guard()`
    """
    try:
        run_query("SELECT 1")
    except Exception as e:  # noqa: BLE001
        st.error(
            "❌ Không kết nối được tới Data Warehouse (PostgreSQL).\n\n"
            f"Chi tiết lỗi: `{e}`\n\n"
            "Kiểm tra lại biến môi trường `POSTGRES_HOST`, `POSTGRES_USER`, "
            "`POSTGRES_PASSWORD`, `POSTGRES_DB` hoặc trạng thái container `postgres-gold`."
        )
        st.stop()
