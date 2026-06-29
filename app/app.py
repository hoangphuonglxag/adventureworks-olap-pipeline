import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query

st.set_page_config(
    page_title="Sales Performance - AdventureWorks",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Topic 3: Hiệu Suất Bán Hàng (Sales Performance)")
st.markdown("---")

# -----------------------------------------------------------------------------
# 1. Doanh Thu / Lợi Nhuận / Biên độ lợi nhuận (Profit Margin)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_sales_kpis():
    # Giả định StandardCost được lưu trong bảng fact hoặc dim_product.
    # Trong mô hình này, doanh thu = total_due, chi phí = sub_total (tạm tính cost từ một góc độ, 
    # thực tế ta nên join với dim_product.standard_cost để tính lợi nhuận gộp).
    # Tuy nhiên ta có fact_product_daily chứa avg_standard_cost.
    # Ta join fact_order với fact_product_daily không dễ vì hạt (grain) khác nhau.
    # Ta hãy join fact_order với dim_product qua product_key (nhưng fact_order không có product_key, fact_order_detail mới có).
    # Đợi đã, fact_order không có product_key (đây là order header).
    # Lợi nhuận cần được tính từ sales_order_detail. Nhưng ở fact_product_daily, ta đã có doanh thu và cost!
    
    query = """
    SELECT 
        SUM(f.revenue) AS total_revenue,
        SUM(f.order_count) AS total_orders,
        SUM(f.gross_profit) AS total_profit
    FROM fact_product_daily f
    """
    return run_query(query).iloc[0]

kpis = get_sales_kpis()
total_rev = kpis['total_revenue'] if pd.notna(kpis['total_revenue']) else 0
total_profit = kpis['total_profit'] if pd.notna(kpis['total_profit']) else 0
profit_margin = (total_profit / total_rev * 100) if total_rev > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Doanh Thu (Revenue)", f"${total_rev:,.0f}")
col2.metric("Lợi Nhuận (Profit)", f"${total_profit:,.0f}")
col3.metric("Biên độ LN (Profit Margin)", f"{profit_margin:.1f}%")
col4.metric("Tổng Số Đơn Hàng", f"{kpis['total_orders']:,.0f}")

st.markdown("---")

# -----------------------------------------------------------------------------
# 2. Doanh thu / Lợi nhuận theo Ngày/Tháng/Năm
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_trend_data():
    query = """
    SELECT 
        d.full_date,
        d.year,
        d.month,
        SUM(f.revenue) AS revenue,
        SUM(f.gross_profit) AS profit
    FROM fact_product_daily f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.full_date, d.year, d.month
    ORDER BY d.full_date
    """
    return run_query(query)

df_trend = get_trend_data()
st.subheader("Doanh thu & Lợi nhuận theo thời gian")
if not df_trend.empty:
    fig_trend = px.line(
        df_trend, 
        x="full_date", 
        y=["revenue", "profit"], 
        title="Xu hướng Doanh thu và Lợi nhuận theo Ngày",
        labels={"full_date": "Ngày", "value": "USD ($)", "variable": "Chỉ số"}
    )
    st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.info("Chưa có dữ liệu Trend.")

# -----------------------------------------------------------------------------
# 3. Giá trị đơn hàng (AOV) B2C vs B2B
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_b2b_b2c_aov():
    query = """
    SELECT 
        c.customer_type,
        COUNT(DISTINCT f.order_id) AS total_orders,
        SUM(f.total_due) AS total_revenue,
        SUM(f.total_due) / NULLIF(COUNT(DISTINCT f.order_id), 0) AS avg_order_value
    FROM fact_order f
    JOIN dim_customer c ON f.customer_key = c.customer_key
    WHERE c.customer_type IN ('Person', 'Store')
    GROUP BY c.customer_type
    """
    return run_query(query)

df_b2x = get_b2b_b2c_aov()
st.subheader("So sánh Giá Trị Đơn Hàng: B2C (Cá nhân) vs B2B (Doanh nghiệp)")
if not df_b2x.empty:
    # Rename for chart
    df_b2x['customer_type'] = df_b2x['customer_type'].map({'Person': 'B2C (Cá nhân)', 'Store': 'B2B (Doanh nghiệp)'})
    
    col_chart, col_data = st.columns([1, 1])
    with col_chart:
        fig_b2x = px.bar(
            df_b2x,
            x="customer_type",
            y="avg_order_value",
            color="customer_type",
            title="Giá trị đơn hàng trung bình (AOV)",
            labels={"customer_type": "Nhóm Khách Hàng", "avg_order_value": "AOV ($)"},
            text_auto='.2s'
        )
        st.plotly_chart(fig_b2x, use_container_width=True)
        
    with col_data:
        fig_pie = px.pie(
            df_b2x, 
            names="customer_type", 
            values="total_revenue", 
            title="Tỷ trọng Doanh Thu B2C vs B2B"
        )
        st.plotly_chart(fig_pie, use_container_width=True)
else:
    st.info("Chưa có dữ liệu B2B/B2C.")
