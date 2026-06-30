"""
Home.py — Trang chủ: tổng quan KPI toàn DW + điều hướng tới 4 nhóm phân tích.
Chạy: streamlit run Home.py
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import streamlit as st

from utils.db import run_query, get_date_bounds, clear_cache, fmt_num, db_connection_guard

st.set_page_config(page_title="Gold DW Dashboard", page_icon="📊", layout="wide")

# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.title("📊 Gold DW Dashboard")
    st.caption("Phân tích dữ liệu tầng Gold — Star Schema (PostgreSQL)")
    st.divider()
    if st.button("🔄 Làm mới dữ liệu (xoá cache)", use_container_width=True):
        clear_cache()
        st.rerun()
    st.caption("Dữ liệu được cache 10 phút mỗi truy vấn để giảm tải DB.")

st.title("📊 Tổng quan Data Warehouse")
st.caption("Tầng Gold · Star Schema · gold_dw")

db_connection_guard()
min_date, max_date = get_date_bounds()

if min_date is None:
    st.warning("Chưa có dữ liệu trong `fact_order_daily` / `dim_date`. Hãy chạy pipeline ETL trước.")
    st.stop()

st.caption(f"Dữ liệu đơn hàng từ **{min_date:%d/%m/%Y}** đến **{max_date:%d/%m/%Y}**")

# ----------------------------------------------------------------------------
# KPI tổng quan (toàn bộ lịch sử)
# ----------------------------------------------------------------------------
kpi_q = """
    SELECT
        (SELECT COALESCE(SUM(daily_revenue), 0) FROM fact_order_daily)            AS total_revenue,
        (SELECT COALESCE(SUM(daily_order_count), 0) FROM fact_order_daily)        AS total_orders,
        (SELECT COUNT(*) FROM dim_customer WHERE is_current = TRUE AND customer_key <> 'UNKNOWN') AS total_customers,
        (SELECT COUNT(*) FROM dim_product  WHERE is_current = TRUE)               AS total_products,
        (SELECT COUNT(*) FROM dim_seller   WHERE is_current = TRUE AND seller_key <> 'UNKNOWN')    AS total_sellers
"""
kpi = run_query(kpi_q).iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💰 Tổng doanh thu", fmt_num(kpi["total_revenue"], 0))
c2.metric("🧾 Tổng số đơn hàng", fmt_num(kpi["total_orders"], 0))
c3.metric("👥 Khách hàng", fmt_num(kpi["total_customers"], 0))
c4.metric("📦 Sản phẩm", fmt_num(kpi["total_products"], 0))
c5.metric("🧑‍💼 Nhân viên bán", fmt_num(kpi["total_sellers"], 0))

st.divider()
st.subheader("Chọn nhóm phân tích")

sections = [
    dict(
        icon="📈",
        title="Doanh thu & Đơn hàng",
        tables="fact_order · fact_order_daily",
        bullets=[
            "Doanh thu theo ngày / tuần / tháng / quý / năm",
            "So sánh kênh bán Online vs Offline",
            "Giá trị đơn hàng trung bình (AOV)",
            "Phân tích chiết khấu, thuế, phí vận chuyển",
            "Tốc độ tăng trưởng và xu hướng",
        ],
        page="pages/1_Doanh_thu_Don_hang.py",
    ),
    dict(
        icon="📦",
        title="Hiệu suất Sản phẩm",
        tables="fact_product_daily · dim_product (SCD2)",
        bullets=[
            "Top/bottom sản phẩm theo doanh thu & số lượng",
            "Biên lợi nhuận gộp (gross profit margin)",
            "Snapshot giá vốn & giá niêm yết theo ngày",
            "Tác động thay đổi giá đến doanh số",
            "Hiệu suất theo danh mục / phân danh mục",
        ],
        page="pages/2_Hieu_suat_San_pham.py",
    ),
    dict(
        icon="👥",
        title="Hành vi Khách hàng",
        tables="fact_customer_behavior · dim_customer (SCD2)",
        bullets=[
            "Phân tích RFM (Recency · Frequency · Monetary)",
            "Phân khúc khách hàng (customer_segment)",
            "Customer Lifetime Value (CLV / LTV)",
            "Tỷ lệ giữ chân & quay lại (retention, cohort)",
            "Khoảng cách giữa các lần mua hàng",
        ],
        page="pages/3_Hanh_vi_Khach_hang.py",
    ),
    dict(
        icon="🧑‍💼",
        title="Hiệu suất Nhân viên bán",
        tables="fact_seller_daily · dim_seller (SCD2)",
        bullets=[
            "Doanh thu & hoa hồng từng nhân viên",
            "Tỷ lệ đạt quota (sales_quota attainment)",
            "Số đơn hàng & khách hàng mỗi nhân viên",
            "Xếp hạng & leaderboard hiệu suất",
            "Lịch sử thay đổi quota / bonus (SCD2)",
        ],
        page="pages/4_Hieu_suat_Nhan_vien.py",
    ),
]

cols = st.columns(2)
for i, sec in enumerate(sections):
    with cols[i % 2]:
        with st.container(border=True):
            st.markdown(f"### {sec['icon']} {sec['title']}")
            st.caption(sec["tables"])
            for b in sec["bullets"]:
                st.markdown(f"- {b}")
            st.page_link(sec["page"], label=f"Mở phân tích {sec['title']} →", icon=sec["icon"])

st.divider()
st.caption(
    "💡 Mỗi trang phân tích đều có bộ lọc thời gian riêng ở sidebar và mục "
    "**🧠 Gợi ý SQL** ở cuối trang để xem truy vấn đã dùng."
)
