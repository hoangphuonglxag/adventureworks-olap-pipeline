import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query

st.set_page_config(page_title="Customer Analysis", page_icon="👥", layout="wide")

st.title("👥 Topic 2: Phân Tích Khách Hàng (Customers)")
st.markdown("---")

# -----------------------------------------------------------------------------
# 1. Phân loại Khách Hàng (Customer Segments)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_segments():
    query = """
    SELECT 
        customer_segment,
        COUNT(customer_key) AS num_customers,
        SUM(total_amount) AS total_revenue
    FROM fact_customer_behavior
    GROUP BY customer_segment
    """
    return run_query(query)

st.subheader("Phân Loại Nhóm Khách Hàng (Segmentation)")
df_seg = get_segments()
if not df_seg.empty:
    col_chart, col_chart2 = st.columns(2)
    with col_chart:
        fig_seg_count = px.pie(
            df_seg, 
            names="customer_segment", 
            values="num_customers", 
            title="Tỷ lệ Khách Hàng theo Nhóm",
            hole=0.4
        )
        st.plotly_chart(fig_seg_count, use_container_width=True)
    with col_chart2:
        fig_seg_rev = px.bar(
            df_seg, 
            x="customer_segment", 
            y="total_revenue", 
            color="customer_segment",
            title="Doanh Thu Đóng Góp Theo Nhóm",
            text_auto='.2s'
        )
        st.plotly_chart(fig_seg_rev, use_container_width=True)
else:
    st.info("Chưa có dữ liệu Customer Behavior.")

st.markdown("---")

# -----------------------------------------------------------------------------
# 2. Khu vực có doanh số tốt nhất
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_top_regions():
    query = """
    SELECT 
        g.country_region_name,
        g.state_province_name,
        SUM(f.total_due) AS total_revenue,
        COUNT(DISTINCT f.customer_key) AS num_customers
    FROM fact_order f
    JOIN dim_customer c ON f.customer_key = c.customer_key
    JOIN dim_geography g ON f.geography_key = g.geography_key
    GROUP BY g.country_region_name, g.state_province_name
    ORDER BY total_revenue DESC
    LIMIT 15
    """
    return run_query(query)

st.subheader("Khu Vực Có Doanh Số Tốt Nhất")
df_region = get_top_regions()
if not df_region.empty:
    fig_region = px.bar(
        df_region,
        x="total_revenue",
        y="state_province_name",
        color="country_region_name",
        orientation='h',
        title="Top 15 Tỉnh/Thành Có Doanh Số Tốt Nhất",
        labels={"total_revenue": "Doanh Thu ($)", "state_province_name": "Tỉnh/Thành", "country_region_name": "Quốc gia"},
        text_auto='.2s'
    )
    fig_region.update_layout(yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig_region, use_container_width=True)
else:
    st.info("Chưa có dữ liệu Khu Vực.")

st.markdown("---")

# -----------------------------------------------------------------------------
# 3. Thói quen mua hàng, khả năng quay lại (RFM Analysis)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_rfm_scatter():
    query = """
    SELECT 
        customer_segment,
        recency_days,
        total_orders,
        total_amount
    FROM fact_customer_behavior
    WHERE total_amount > 0
    """
    return run_query(query)

st.subheader("Thói Quen Mua Hàng & Khả Năng Quay Lại (RFM)")
st.markdown("> **Trục ngang (Recency):** Số ngày kể từ lần mua cuối. Càng nhỏ thì khả năng quay lại/trung thành càng cao.\n"
            "> **Trục dọc (Monetary):** Tổng tiền đã chi tiêu.\n"
            "> **Kích thước bóng:** Số lượng đơn hàng (Frequency).")
df_rfm = get_rfm_scatter()
if not df_rfm.empty:
    # Lọc bớt outliers để biểu đồ dễ nhìn
    df_rfm = df_rfm[df_rfm['total_amount'] < df_rfm['total_amount'].quantile(0.99)]
    
    fig_scatter = px.scatter(
        df_rfm,
        x="recency_days",
        y="total_amount",
        size="total_orders",
        color="customer_segment",
        hover_data=["total_orders"],
        title="Ma trận Khách Hàng (Recency vs Monetary)",
        labels={"recency_days": "Số ngày từ lần mua cuối (Recency)", "total_amount": "Tổng chi tiêu ($)"},
        opacity=0.6
    )
    st.plotly_chart(fig_scatter, use_container_width=True)
else:
    st.info("Chưa có dữ liệu chi tiết thói quen mua hàng.")
