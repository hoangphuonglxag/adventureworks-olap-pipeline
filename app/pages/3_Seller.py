import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query

st.set_page_config(page_title="Seller Performance", page_icon="👔", layout="wide")

st.title("👔 Topic 4: Hiệu Suất Bán Hàng Nhân Sự (Sellers)")
st.markdown("---")

# -----------------------------------------------------------------------------
# 1. Nhân viên có doanh số tốt nhất
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_top_sellers():
    query = """
    SELECT 
        s.seller_name,
        SUM(f.revenue) AS total_revenue,
        SUM(f.order_count) AS total_orders
    FROM fact_seller_daily f
    JOIN dim_seller s ON f.seller_key = s.seller_key
    WHERE s.seller_id != -1
    GROUP BY s.seller_name
    ORDER BY total_revenue DESC
    LIMIT 10
    """
    return run_query(query)

st.subheader("Nhân Viên Có Doanh Số Tốt Nhất")
df_sellers = get_top_sellers()
if not df_sellers.empty:
    fig_sellers = px.bar(
        df_sellers,
        x="total_revenue",
        y="seller_name",
        orientation='h',
        title="Top Nhân Viên Bán Hàng",
        labels={"total_revenue": "Doanh Thu ($)", "seller_name": "Nhân Viên"},
        text_auto='.2s',
        color="total_revenue",
        color_continuous_scale="Blues"
    )
    fig_sellers.update_layout(yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig_sellers, use_container_width=True)
else:
    st.info("Chưa có dữ liệu Nhân sự.")

st.markdown("---")

# -----------------------------------------------------------------------------
# Chọn một Seller cụ thể để xem chi tiết
# -----------------------------------------------------------------------------
if not df_sellers.empty:
    seller_list = df_sellers['seller_name'].tolist()
    selected_seller = st.selectbox("Chọn nhân viên để xem chi tiết:", seller_list)

    # 2. Top sản phẩm của nhân viên
    @st.cache_data(ttl=600)
    def get_seller_top_products(seller_name):
        query = f"""
        SELECT 
            p.product_name,
            SUM(fd.total_due) AS revenue,
            COUNT(fd.order_id) AS num_orders
        FROM fact_order fd
        JOIN dim_seller s ON fd.seller_key = s.seller_key
        JOIN dim_customer c ON fd.customer_key = c.customer_key
        /* Tạm dùng doanh thu order tổng quát của seller vì 
           hiện tại fact_order_detail chưa được đưa lên data warehouse chi tiết.
           Nếu có fact_order_detail ta sẽ lấy được product_name trực tiếp.
           Do fact_order là header nên query dưới đây chỉ minh họa. 
        */
        WHERE s.seller_name = '{seller_name}'
        GROUP BY p.product_name
        ORDER BY revenue DESC
        LIMIT 5
        """
        # Sửa query lại vì không join được product từ fact_order
        query_fix = f"""
        -- Vì AdventureWorks OLAP chưa có fact_order_detail, ta không lấy được trực tiếp product mà seller bán.
        -- Thay vào đó, lấy Danh mục lãnh thổ hoặc loại khách hàng mà seller bán tốt nhất.
        SELECT 
            g.country_region_name AS territory,
            SUM(fd.total_due) AS revenue
        FROM fact_order fd
        JOIN dim_seller s ON fd.seller_key = s.seller_key
        JOIN dim_customer c ON fd.customer_key = c.customer_key
        JOIN dim_geography g ON fd.geography_key = g.geography_key
        WHERE s.seller_name = '{seller_name}'
        GROUP BY g.country_region_name
        ORDER BY revenue DESC
        LIMIT 5
        """
        return run_query(query_fix)

    # 3. Nhóm khách hàng của nhân viên
    @st.cache_data(ttl=600)
    def get_seller_customer_segments(seller_name):
        query = f"""
        SELECT 
            cb.customer_segment,
            COUNT(DISTINCT fd.customer_key) AS num_customers,
            SUM(fd.total_due) AS revenue
        FROM fact_order fd
        JOIN dim_seller s ON fd.seller_key = s.seller_key
        JOIN fact_customer_behavior cb ON fd.customer_key = cb.customer_key
        WHERE s.seller_name = '{seller_name}'
        GROUP BY cb.customer_segment
        """
        return run_query(query)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader(f"Khu vực bán tốt nhất của {selected_seller}")
        df_prod = get_seller_top_products(selected_seller)
        if not df_prod.empty:
            fig_p = px.pie(df_prod, names="territory", values="revenue", hole=0.4)
            st.plotly_chart(fig_p, use_container_width=True)
            st.caption("*Do fact table hiện tại ở mức order header, ta thay thế top sản phẩm bằng top khu vực mà nhân viên phụ trách.*")
        else:
            st.info("Không có dữ liệu.")
            
    with col2:
        st.subheader(f"Tập khách hàng của {selected_seller}")
        df_cust = get_seller_customer_segments(selected_seller)
        if not df_cust.empty:
            fig_c = px.bar(
                df_cust, 
                x="customer_segment", 
                y="revenue", 
                color="customer_segment",
                title="Doanh thu theo Nhóm Khách Hàng (RFM)",
                text_auto='.2s'
            )
            st.plotly_chart(fig_c, use_container_width=True)
        else:
            st.info("Không có dữ liệu.")
