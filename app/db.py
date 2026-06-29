import os
import streamlit as st
from sqlalchemy import create_engine
import pandas as pd

@st.cache_resource
def get_engine():
    """
    Tạo kết nối SQLAlchemy đến PostgreSQL Data Warehouse.
    Sử dụng @st.cache_resource để tái sử dụng engine pool giữa các lượt tải trang.
    """
    user = os.getenv("POSTGRES_USER", "gold_user")
    password = os.getenv("POSTGRES_PASSWORD", "adminpassword")
    db = "adventureworks_dw"
    
    # Khi chạy trong Docker, host là tên service: postgres-gold
    # Nếu chạy local ngoài Docker, cần chỉnh thành localhost
    host = os.getenv("POSTGRES_HOST", "postgres-gold")
    port = "5432"

    url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(url)
    return engine

@st.cache_data(ttl=600)  # Cache kết quả query 10 phút
def run_query(query: str) -> pd.DataFrame:
    """
    Thực thi câu truy vấn SQL và trả về Pandas DataFrame.
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df
