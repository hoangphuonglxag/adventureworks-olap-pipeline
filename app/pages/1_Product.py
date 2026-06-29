import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query

st.set_page_config(page_title="Product Analysis", page_icon="📦", layout="wide")

st.title("📦 Topic 1: Phân Tích Sản Phẩm (Products)")
st.markdown("---")

# -----------------------------------------------------------------------------
# 1. Sản phẩm có doanh số tốt nhất
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_top_products():
    query = """
    SELECT 
        p.product_name,
        SUM(f.revenue) AS total_revenue,
        SUM(f.quantity_sold) AS total_quantity
    FROM fact_product_daily f
    JOIN dim_product p ON f.product_key = p.product_key
    GROUP BY p.product_name
    ORDER BY total_revenue DESC
    LIMIT 10
    """
    return run_query(query)

df_top_prod = get_top_products()
st.subheader("Top 10 Sản Phẩm Có Doanh Số Tốt Nhất")
if not df_top_prod.empty:
    fig_prod = px.bar(
        df_top_prod, 
        x="total_revenue", 
        y="product_name", 
        orientation='h',
        title="Doanh Thu Theo Sản Phẩm",
        labels={"total_revenue": "Doanh Thu ($)", "product_name": "Sản Phẩm"},
        text_auto='.2s'
    )
    fig_prod.update_layout(yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig_prod, use_container_width=True)
else:
    st.info("Chưa có dữ liệu.")

st.markdown("---")

# -----------------------------------------------------------------------------
# 2. Sản phẩm theo khu vực & B2B/B2C
# -----------------------------------------------------------------------------
col_geo, col_b2x = st.columns(2)

@st.cache_data(ttl=600)
def get_product_geo():
    query = """
    SELECT 
        g.country_region_name,
        p.category_name,
        SUM(f.total_due) AS total_revenue
    FROM fact_order f
    JOIN dim_customer c ON f.customer_key = c.customer_key
    JOIN dim_geography g ON c.geography_key = g.geography_key
    JOIN fact_order_daily fd ON fd.date_key = f.date_key -- Lấy thông tin phụ nếu cần
    /* Thực tế fact_order không có product_key, để xem category theo region ta cần fact chứa region + product.
       Tạm thời query mẫu từ fact_order. (Do fact_order là Header) 
       Để lấy product, ta nên có fact_order_detail. OLAP hiện tại không lưu fact_order_detail mà pre-aggregate thành fact_product_daily (chưa có dimension geography!). 
       Do hạn chế OLAP schema hiện tại, ta sẽ query tạm Top quốc gia tổng quát.
    */
    GROUP BY g.country_region_name, p.category_name
    """
    # Fix query để dùng fact_order (không có product)
    query_fix = """
    SELECT 
        g.country_region_name,
        SUM(f.total_due) AS total_revenue
    FROM fact_order f
    JOIN dim_customer c ON f.customer_key = c.customer_key
    JOIN dim_geography g ON c.geography_key = g.geography_key
    GROUP BY g.country_region_name
    ORDER BY total_revenue DESC
    """
    return run_query(query_fix)

@st.cache_data(ttl=600)
def get_product_b2x():
    query = """
    SELECT 
        c.customer_type,
        SUM(f.total_due) AS total_revenue
    FROM fact_order f
    JOIN dim_customer c ON f.customer_key = c.customer_key
    WHERE c.customer_type IN ('Person', 'Store')
    GROUP BY c.customer_type
    """
    return run_query(query)

with col_geo:
    st.subheader("Doanh Số Theo Khu Vực")
    df_geo = get_product_geo()
    if not df_geo.empty:
        fig_geo = px.pie(df_geo, names="country_region_name", values="total_revenue", hole=0.4)
        st.plotly_chart(fig_geo, use_container_width=True)

with col_b2x:
    st.subheader("Doanh Số B2C vs B2B")
    df_b2x = get_product_b2x()
    if not df_b2x.empty:
        df_b2x['customer_type'] = df_b2x['customer_type'].map({'Person': 'B2C', 'Store': 'B2B'})
        fig_b2x = px.bar(df_b2x, x="customer_type", y="total_revenue", color="customer_type", text_auto='.2s')
        st.plotly_chart(fig_b2x, use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# 3. Tỉ lệ tồn kho & Cảnh báo cháy hàng
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_inventory():
    query = """
    WITH sales AS (
        SELECT product_key, SUM(quantity_sold) as total_sold
        FROM fact_product_daily
        GROUP BY product_key
    ),
    inv AS (
        SELECT product_key, SUM(quantity) as current_stock
        FROM fact_inventory
        GROUP BY product_key
    )
    SELECT 
        p.product_id,
        p.product_name,
        COALESCE(i.current_stock, 0) AS stock,
        COALESCE(s.total_sold, 0) AS sold
    FROM dim_product p
    LEFT JOIN inv i ON p.product_key = i.product_key
    LEFT JOIN sales s ON p.product_key = s.product_key
    WHERE p.is_current = True
    ORDER BY stock ASC
    LIMIT 20
    """
    return run_query(query)

st.subheader("⚠️ Cảnh Báo Tồn Kho (Cháy Hàng)")
df_inv = get_inventory()
if not df_inv.empty:
    df_low_stock = df_inv[df_inv['stock'] < 50] # Threshold cháy hàng
    if not df_low_stock.empty:
        st.warning(f"Có {len(df_low_stock)} sản phẩm đang ở mức Tồn kho thấp (< 50)!")
        fig_inv = px.bar(
            df_low_stock,
            x="stock",
            y="product_name",
            orientation='h',
            title="Các Sản Phẩm Sắp Hết Hàng",
            color="stock",
            color_continuous_scale="Reds_r"
        )
        st.plotly_chart(fig_inv, use_container_width=True)
    else:
        st.success("Tình trạng kho hàng ổn định. Không có sản phẩm nào sắp hết hàng.")
    
    st.dataframe(df_inv, use_container_width=True)
else:
    st.info("Chưa có dữ liệu tồn kho.")
