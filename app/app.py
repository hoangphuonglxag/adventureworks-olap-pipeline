# =============================================================================
# app/app.py
# Streamlit Dashboard — AdventureWorks OLAP Pipeline
#
# 4 Tab chính:
#   📊 Executive Summary  |  💰 Sales Analysis
#   👤 Customer Analytics |  📦 Product & Inventory
# =============================================================================

import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from db import get_engine, run_query

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AdventureWorks BI Dashboard",
    page_icon="🏔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL STYLES
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Dark sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
}
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
[data-testid="stSidebar"] .stSelectbox label { color: #94a3b8 !important; font-size: 0.78rem; }

/* KPI Cards */
.kpi-card {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 20px 24px;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
}
.kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 30px rgba(99,102,241,0.25);
    border-color: #6366f1;
}
.kpi-value {
    font-size: 2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #6366f1, #818cf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.kpi-label {
    font-size: 0.78rem;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 4px;
}
.kpi-delta {
    font-size: 0.82rem;
    margin-top: 6px;
}
.kpi-delta.up   { color: #22c55e; }
.kpi-delta.down { color: #ef4444; }

/* Section headers */
.section-header {
    font-size: 1.05rem;
    font-weight: 600;
    color: #e2e8f0;
    padding: 8px 0 4px 0;
    border-bottom: 2px solid #334155;
    margin-bottom: 16px;
}

/* Tabs */
[data-testid="stTabs"] [data-baseweb="tab"] {
    font-size: 0.9rem;
    font-weight: 500;
}

/* Main background */
.main .block-container {
    background: #0f172a;
    padding-top: 1.5rem;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# CHART THEME — plotly dark style nhất quán
# ─────────────────────────────────────────────────────────────────────────────
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(15,23,42,0.6)",
    font=dict(family="Inter", color="#94a3b8", size=12),
    title_font=dict(color="#e2e8f0", size=14),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#334155"),
    xaxis=dict(gridcolor="#1e293b", linecolor="#334155", tickfont=dict(color="#64748b")),
    yaxis=dict(gridcolor="#1e293b", linecolor="#334155", tickfont=dict(color="#64748b")),
    margin=dict(t=40, b=30, l=20, r=20),
)
COLOR_SEQ = px.colors.qualitative.Vivid
COLOR_BLUE = "#6366f1"
COLOR_GREEN = "#22c55e"
COLOR_AMBER = "#f59e0b"


def apply_theme(fig) -> go.Figure:
    fig.update_layout(**CHART_LAYOUT)
    return fig


def fmt_currency(val: float) -> str:
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"${val/1_000:.0f}K"
    return f"${val:.0f}"


def fmt_number(val: float) -> str:
    if val >= 1_000_000:
        return f"{val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"{val/1_000:.1f}K"
    return str(int(val))


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — Bộ lọc toàn cục
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏔️ AdventureWorks")
    st.markdown("**OLAP BI Dashboard**")
    st.markdown("---")

    # Lấy min/max year từ dim_date
    try:
        year_range_df = run_query("SELECT MIN(year) as min_y, MAX(year) as max_y FROM dim_date WHERE year BETWEEN 2010 AND 2030")
        min_year = int(year_range_df["min_y"].iloc[0]) if not year_range_df.empty else 2011
        max_year = int(year_range_df["max_y"].iloc[0]) if not year_range_df.empty else 2014
    except Exception:
        min_year, max_year = 2011, 2014

    # Thực tế AdventureWorks có data 2011-2014
    fact_years_df = run_query("""
        SELECT DISTINCT d.year
        FROM fact_order fo
        JOIN dim_date d ON fo.date_key = d.date_key
        ORDER BY d.year
    """) if True else pd.DataFrame({"year": [2011,2012,2013,2014]})

    available_years = sorted(fact_years_df["year"].tolist()) if not fact_years_df.empty else [2011,2012,2013,2014]

    st.markdown("### 📅 Bộ lọc thời gian")
    if len(available_years) >= 2:
        selected_years = st.select_slider(
            "Năm",
            options=available_years,
            value=(available_years[0], available_years[-1]),
        )
        year_from, year_to = selected_years
    else:
        year_from = year_to = available_years[0] if available_years else 2011

    # Lọc theo kênh bán
    st.markdown("### 🛒 Kênh bán hàng")
    channels_df = run_query("SELECT DISTINCT sales_channel FROM fact_order WHERE sales_channel IS NOT NULL ORDER BY 1")
    channels = ["Tất cả"] + (channels_df["sales_channel"].tolist() if not channels_df.empty else ["Online", "Store"])
    selected_channel = st.selectbox("Kênh", channels)

    st.markdown("---")
    st.markdown("""
<div style='font-size:0.75rem; color:#475569;'>
Nguồn dữ liệu:<br>
🗄️ SQL Server 2022 (OLTP)<br>
🪣 MinIO (Data Lake)<br>
🐘 PostgreSQL (Gold DW)<br><br>
⚙️ Engine: Apache Spark 3.5
</div>
""", unsafe_allow_html=True)

    if st.button("🔄 Refresh dữ liệu", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SQL HELPER — tự động inject filter năm & kênh
# ─────────────────────────────────────────────────────────────────────────────
def channel_filter() -> str:
    if selected_channel != "Tất cả":
        return f"AND fo.sales_channel = '{selected_channel}'"
    return ""


def year_filter_date() -> str:
    return f"AND d.year BETWEEN {year_from} AND {year_to}"


def year_filter_key() -> str:
    return f"""AND fo.date_key IN (
        SELECT date_key FROM dim_date WHERE year BETWEEN {year_from} AND {year_to}
    )"""


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<h1 style='margin-bottom:0; font-size:1.8rem; font-weight:700;
   background:linear-gradient(135deg,#6366f1,#818cf8,#38bdf8);
   -webkit-background-clip:text; -webkit-text-fill-color:transparent;
   background-clip:text;'>
    🏔️ AdventureWorks BI Dashboard
</h1>
<p style='color:#64748b; margin-top:4px; font-size:0.88rem;'>
    Star Schema · Spark · MinIO · PostgreSQL — Period: {year_from} – {year_to}
    {"· Channel: " + selected_channel if selected_channel != "Tất cả" else ""}
</p>
<hr style='border-color:#1e293b; margin:12px 0;'>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Executive Summary",
    "💰 Sales Analysis",
    "👤 Customer Analytics",
    "📦 Product & Inventory",
])


# =============================================================================
# TAB 1: EXECUTIVE SUMMARY
# =============================================================================
with tab1:
    # ── KPI Cards ──
    kpi_sql = f"""
    SELECT
        COALESCE(SUM(fo.total_due), 0)              AS total_revenue,
        COUNT(DISTINCT fo.order_id)                  AS total_orders,
        COUNT(DISTINCT fo.customer_key)              AS total_customers,
        COALESCE(AVG(fo.total_due), 0)               AS avg_order_value,
        COALESCE(SUM(fo.total_due - fo.tax_amt - fo.freight_amt), 0) AS net_revenue
    FROM fact_order fo
    JOIN dim_date d ON fo.date_key = d.date_key
    WHERE 1=1
      {year_filter_date()}
      {channel_filter()}
    """

    try:
        kpi = run_query(kpi_sql).iloc[0]
        total_rev  = float(kpi["total_revenue"])
        total_ord  = int(kpi["total_orders"])
        total_cust = int(kpi["total_customers"])
        avg_ov     = float(kpi["avg_order_value"])
        net_rev    = float(kpi["net_revenue"])
    except Exception as e:
        st.error(f"Lỗi load KPI: {e}")
        total_rev = total_ord = total_cust = avg_ov = net_rev = 0

    col1, col2, col3, col4, col5 = st.columns(5)
    kpi_data = [
        (col1, "💵 Tổng Doanh Thu", fmt_currency(total_rev), "kpi-value"),
        (col2, "📦 Tổng Đơn Hàng", fmt_number(total_ord),   "kpi-value"),
        (col3, "👤 Khách Hàng",     fmt_number(total_cust),  "kpi-value"),
        (col4, "💳 AOV",            fmt_currency(avg_ov),    "kpi-value"),
        (col5, "🏦 Doanh Thu Ròng", fmt_currency(net_rev),   "kpi-value"),
    ]
    for col, label, value, cls in kpi_data:
        with col:
            st.markdown(f"""
<div class="kpi-card">
    <div class="{cls}">{value}</div>
    <div class="kpi-label">{label}</div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Revenue Trend (Monthly) ──
    col_trend, col_channel = st.columns([3, 2])

    with col_trend:
        st.markdown('<div class="section-header">📈 Xu hướng Doanh Thu theo Tháng</div>', unsafe_allow_html=True)
        trend_sql = f"""
        SELECT
            d.year,
            d.month,
            d.month_name,
            SUM(fo.total_due) AS monthly_revenue,
            COUNT(DISTINCT fo.order_id) AS order_count
        FROM fact_order fo
        JOIN dim_date d ON fo.date_key = d.date_key
        WHERE 1=1
          {year_filter_date()}
          {channel_filter()}
        GROUP BY d.year, d.month, d.month_name
        ORDER BY d.year, d.month
        """
        try:
            trend_df = run_query(trend_sql)
            if not trend_df.empty:
                trend_df["period"] = trend_df["year"].astype(str) + "-" + trend_df["month"].astype(str).str.zfill(2)
                fig_trend = make_subplots(specs=[[{"secondary_y": True}]])
                fig_trend.add_trace(
                    go.Bar(
                        x=trend_df["period"],
                        y=trend_df["monthly_revenue"],
                        name="Revenue",
                        marker_color=COLOR_BLUE,
                        opacity=0.85,
                    ),
                    secondary_y=False,
                )
                fig_trend.add_trace(
                    go.Scatter(
                        x=trend_df["period"],
                        y=trend_df["order_count"],
                        name="Orders",
                        mode="lines+markers",
                        line=dict(color=COLOR_AMBER, width=2),
                        marker=dict(size=5),
                    ),
                    secondary_y=True,
                )
                fig_trend.update_layout(
                    **CHART_LAYOUT,
                    height=340,
                    showlegend=True,
                    xaxis=dict(tickangle=45, **CHART_LAYOUT["xaxis"]),
                )
                fig_trend.update_yaxes(title_text="Revenue ($)", secondary_y=False, gridcolor="#1e293b")
                fig_trend.update_yaxes(title_text="Orders", secondary_y=True, gridcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.info("Chưa có dữ liệu trend.")
        except Exception as e:
            st.error(f"Lỗi trend chart: {e}")

    with col_channel:
        st.markdown('<div class="section-header">🛒 Doanh Thu theo Kênh</div>', unsafe_allow_html=True)
        channel_sql = f"""
        SELECT
            COALESCE(fo.sales_channel, 'Unknown') AS sales_channel,
            SUM(fo.total_due)                      AS revenue,
            COUNT(DISTINCT fo.order_id)            AS orders
        FROM fact_order fo
        JOIN dim_date d ON fo.date_key = d.date_key
        WHERE 1=1
          {year_filter_date()}
        GROUP BY fo.sales_channel
        ORDER BY revenue DESC
        """
        try:
            ch_df = run_query(channel_sql)
            if not ch_df.empty:
                fig_ch = px.pie(
                    ch_df,
                    values="revenue",
                    names="sales_channel",
                    hole=0.55,
                    color_discrete_sequence=COLOR_SEQ,
                )
                fig_ch.update_traces(textposition="outside", textinfo="percent+label")
                fig_ch.update_layout(**CHART_LAYOUT, height=340, showlegend=True)
                st.plotly_chart(fig_ch, use_container_width=True)
        except Exception as e:
            st.error(f"Lỗi channel chart: {e}")

    # ── Revenue by Territory ──
    st.markdown('<div class="section-header">🗺️ Doanh Thu theo Khu vực (Territory)</div>', unsafe_allow_html=True)
    territory_sql = f"""
    SELECT
        COALESCE(g.territory_name, 'Unknown') AS territory,
        COALESCE(g.territory_group, 'Unknown') AS territory_group,
        SUM(fo.total_due)                      AS revenue,
        COUNT(DISTINCT fo.order_id)            AS orders
    FROM fact_order fo
    JOIN dim_date d      ON fo.date_key      = d.date_key
    LEFT JOIN dim_geography g ON fo.geography_key = g.geography_key
    WHERE 1=1
      {year_filter_date()}
      {channel_filter()}
    GROUP BY g.territory_name, g.territory_group
    ORDER BY revenue DESC
    LIMIT 15
    """
    try:
        terr_df = run_query(territory_sql)
        if not terr_df.empty:
            fig_terr = px.bar(
                terr_df,
                x="revenue", y="territory",
                color="territory_group",
                orientation="h",
                color_discrete_sequence=COLOR_SEQ,
                text=terr_df["revenue"].apply(fmt_currency),
            )
            fig_terr.update_traces(textposition="outside")
            fig_terr.update_layout(**CHART_LAYOUT, height=420)
            st.plotly_chart(fig_terr, use_container_width=True)
    except Exception as e:
        st.error(f"Lỗi territory: {e}")


# =============================================================================
# TAB 2: SALES ANALYSIS
# =============================================================================
with tab2:
    col_left, col_right = st.columns(2)

    # ── Top Sellers ──
    with col_left:
        st.markdown('<div class="section-header">🏆 Top 10 Nhân Viên Sales</div>', unsafe_allow_html=True)
        seller_sql = f"""
        SELECT
            ds.seller_name,
            SUM(fsd.revenue)       AS total_revenue,
            SUM(fsd.order_count)   AS total_orders,
            SUM(fsd.commission_earned) AS total_commission
        FROM fact_seller_daily fsd
        JOIN dim_seller  ds ON fsd.seller_key = ds.seller_key
        JOIN dim_date     d ON fsd.date_key   = d.date_key
        WHERE ds.seller_name != 'Unknown / N/A'
          AND ds.is_current = TRUE
          {year_filter_date().replace('fo.', '')}
        GROUP BY ds.seller_name
        ORDER BY total_revenue DESC
        LIMIT 10
        """
        try:
            seller_df = run_query(seller_sql)
            if not seller_df.empty:
                fig_seller = px.bar(
                    seller_df,
                    x="total_revenue", y="seller_name",
                    orientation="h",
                    color="total_revenue",
                    color_continuous_scale="Viridis",
                    text=seller_df["total_revenue"].apply(fmt_currency),
                )
                fig_seller.update_traces(textposition="outside")
                fig_seller.update_layout(**CHART_LAYOUT, height=400, coloraxis_showscale=False)
                st.plotly_chart(fig_seller, use_container_width=True)
            else:
                st.info("Chưa có dữ liệu seller.")
        except Exception as e:
            st.error(f"Lỗi seller chart: {e}")

    # ── Daily Sales Trend ──
    with col_right:
        st.markdown('<div class="section-header">📅 Daily Revenue Trend</div>', unsafe_allow_html=True)
        daily_sql = f"""
        SELECT
            d.full_date,
            fod.daily_revenue,
            fod.daily_order_count,
            fod.average_order_value
        FROM fact_order_daily fod
        JOIN dim_date d ON fod.date_key = d.date_key
        WHERE 1=1
          {year_filter_date()}
        ORDER BY d.full_date
        """
        try:
            daily_df = run_query(daily_sql)
            if not daily_df.empty:
                daily_df["full_date"] = pd.to_datetime(daily_df["full_date"])
                # Rolling 7-day average
                daily_df = daily_df.sort_values("full_date")
                daily_df["ma7"] = daily_df["daily_revenue"].rolling(7, min_periods=1).mean()

                fig_daily = go.Figure()
                fig_daily.add_trace(go.Scatter(
                    x=daily_df["full_date"], y=daily_df["daily_revenue"],
                    mode="lines", name="Daily Revenue",
                    line=dict(color=COLOR_BLUE, width=1), opacity=0.4,
                ))
                fig_daily.add_trace(go.Scatter(
                    x=daily_df["full_date"], y=daily_df["ma7"],
                    mode="lines", name="7-Day MA",
                    line=dict(color=COLOR_AMBER, width=2.5),
                ))
                fig_daily.update_layout(**CHART_LAYOUT, height=400)
                st.plotly_chart(fig_daily, use_container_width=True)
            else:
                st.info("Chưa có dữ liệu daily.")
        except Exception as e:
            st.error(f"Lỗi daily chart: {e}")

    # ── YoY Comparison ──
    st.markdown('<div class="section-header">📊 So Sánh Doanh Thu Theo Quý (YoY)</div>', unsafe_allow_html=True)
    yoy_sql = f"""
    SELECT
        d.year,
        d.quarter,
        SUM(fo.total_due) AS quarterly_revenue,
        COUNT(DISTINCT fo.order_id) AS orders
    FROM fact_order fo
    JOIN dim_date d ON fo.date_key = d.date_key
    WHERE 1=1
      {year_filter_date()}
      {channel_filter()}
    GROUP BY d.year, d.quarter
    ORDER BY d.year, d.quarter
    """
    try:
        yoy_df = run_query(yoy_sql)
        if not yoy_df.empty:
            yoy_df["quarter_label"] = "Q" + yoy_df["quarter"].astype(str)
            fig_yoy = px.bar(
                yoy_df,
                x="quarter_label", y="quarterly_revenue",
                color=yoy_df["year"].astype(str),
                barmode="group",
                color_discrete_sequence=COLOR_SEQ,
                text=yoy_df["quarterly_revenue"].apply(fmt_currency),
            )
            fig_yoy.update_traces(textposition="outside")
            fig_yoy.update_layout(**CHART_LAYOUT, height=350)
            st.plotly_chart(fig_yoy, use_container_width=True)
    except Exception as e:
        st.error(f"Lỗi YoY: {e}")


# =============================================================================
# TAB 3: CUSTOMER ANALYTICS
# =============================================================================
with tab3:
    col_seg, col_top = st.columns([2, 3])

    # ── Customer Segments (RFM/KMeans) ──
    with col_seg:
        st.markdown('<div class="section-header">🎯 Phân Khúc Khách Hàng (KMeans)</div>', unsafe_allow_html=True)
        seg_sql = """
        SELECT
            COALESCE(customer_segment, 'Unclassified') AS segment,
            COUNT(*) AS customer_count,
            AVG(total_amount) AS avg_revenue,
            AVG(recency_days) AS avg_recency
        FROM fact_customer_behavior
        GROUP BY customer_segment
        ORDER BY customer_count DESC
        """
        try:
            seg_df = run_query(seg_sql)
            if not seg_df.empty:
                fig_seg = px.pie(
                    seg_df,
                    values="customer_count",
                    names="segment",
                    hole=0.5,
                    color_discrete_sequence=COLOR_SEQ,
                )
                fig_seg.update_traces(textposition="outside", textinfo="percent+label+value")
                fig_seg.update_layout(**CHART_LAYOUT, height=380)
                st.plotly_chart(fig_seg, use_container_width=True)

                # Segment stats table
                seg_df["avg_revenue"] = seg_df["avg_revenue"].apply(fmt_currency)
                seg_df["avg_recency"] = seg_df["avg_recency"].apply(lambda x: f"{int(x)}d")
                st.dataframe(
                    seg_df[["segment", "customer_count", "avg_revenue", "avg_recency"]].rename(columns={
                        "segment": "Phân khúc",
                        "customer_count": "Số KH",
                        "avg_revenue": "Avg Revenue",
                        "avg_recency": "Avg Recency",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
        except Exception as e:
            st.error(f"Lỗi segment: {e}")

    # ── Top Customers ──
    with col_top:
        st.markdown('<div class="section-header">👑 Top 15 Khách Hàng Theo Doanh Thu</div>', unsafe_allow_html=True)
        top_cust_sql = f"""
        SELECT
            dc.customer_name,
            dc.customer_type,
            fcb.total_orders,
            fcb.total_amount,
            fcb.avg_order_value,
            fcb.recency_days,
            COALESCE(fcb.customer_segment, 'N/A') AS segment
        FROM fact_customer_behavior fcb
        JOIN dim_customer dc ON fcb.customer_key = dc.customer_key
        WHERE dc.customer_name != 'Unknown / N/A'
          AND dc.is_current = TRUE
        ORDER BY fcb.total_amount DESC
        LIMIT 15
        """
        try:
            top_df = run_query(top_cust_sql)
            if not top_df.empty:
                fig_top = px.scatter(
                    top_df,
                    x="total_orders",
                    y="total_amount",
                    size="avg_order_value",
                    color="segment",
                    hover_name="customer_name",
                    hover_data={"recency_days": True, "customer_type": True},
                    color_discrete_sequence=COLOR_SEQ,
                    size_max=40,
                )
                fig_top.update_layout(
                    **CHART_LAYOUT,
                    height=380,
                    xaxis_title="Số Đơn Hàng",
                    yaxis_title="Tổng Doanh Thu ($)",
                )
                st.plotly_chart(fig_top, use_container_width=True)
        except Exception as e:
            st.error(f"Lỗi top customers: {e}")

    # ── Customer Behavior Stats ──
    st.markdown('<div class="section-header">📉 Phân Phối Recency & Monetary</div>', unsafe_allow_html=True)
    col_rec, col_mon = st.columns(2)

    with col_rec:
        rfm_sql = """
        SELECT recency_days, total_orders, total_amount, customer_segment
        FROM fact_customer_behavior
        WHERE recency_days IS NOT NULL
          AND recency_days < 2000
        """
        try:
            rfm_df = run_query(rfm_sql)
            if not rfm_df.empty:
                fig_rec = px.histogram(
                    rfm_df, x="recency_days",
                    nbins=30, color_discrete_sequence=[COLOR_BLUE],
                    labels={"recency_days": "Số ngày kể từ đơn cuối"},
                )
                fig_rec.update_layout(**CHART_LAYOUT, height=280, title="Recency Distribution")
                st.plotly_chart(fig_rec, use_container_width=True)
        except Exception as e:
            st.error(f"Lỗi recency: {e}")

    with col_mon:
        try:
            rfm_df2 = run_query("""
                SELECT total_amount, customer_segment
                FROM fact_customer_behavior
                WHERE total_amount IS NOT NULL AND total_amount > 0
            """)
            if not rfm_df2.empty:
                fig_mon = px.box(
                    rfm_df2, x="customer_segment", y="total_amount",
                    color="customer_segment",
                    color_discrete_sequence=COLOR_SEQ,
                    points=False,
                )
                fig_mon.update_layout(**CHART_LAYOUT, height=280, title="Revenue by Segment", showlegend=False)
                st.plotly_chart(fig_mon, use_container_width=True)
        except Exception as e:
            st.error(f"Lỗi monetary box: {e}")


# =============================================================================
# TAB 4: PRODUCT & INVENTORY
# =============================================================================
with tab4:
    col_prod, col_cat = st.columns([3, 2])

    # ── Top Products by Revenue ──
    with col_prod:
        st.markdown('<div class="section-header">🥇 Top 15 Sản Phẩm Theo Doanh Thu</div>', unsafe_allow_html=True)
        prod_sql = f"""
        SELECT
            dp.product_name,
            dp.category_name,
            dp.subcategory_name,
            SUM(fpd.revenue)       AS total_revenue,
            SUM(fpd.gross_profit)  AS total_profit,
            SUM(fpd.quantity_sold) AS total_qty,
            CASE
                WHEN SUM(fpd.revenue) > 0
                THEN ROUND(SUM(fpd.gross_profit)::numeric / SUM(fpd.revenue) * 100, 1)
                ELSE 0
            END AS margin_pct
        FROM fact_product_daily fpd
        JOIN dim_product dp ON fpd.product_key = dp.product_key
        JOIN dim_date d      ON fpd.date_key    = d.date_key
        WHERE dp.is_current = TRUE
          {year_filter_date()}
        GROUP BY dp.product_name, dp.category_name, dp.subcategory_name
        ORDER BY total_revenue DESC
        LIMIT 15
        """
        try:
            prod_df = run_query(prod_sql)
            if not prod_df.empty:
                fig_prod = px.bar(
                    prod_df,
                    x="total_revenue", y="product_name",
                    color="margin_pct",
                    color_continuous_scale="RdYlGn",
                    orientation="h",
                    text=prod_df["total_revenue"].apply(fmt_currency),
                    hover_data={"total_qty": True, "margin_pct": ":.1f%", "category_name": True},
                )
                fig_prod.update_traces(textposition="outside")
                fig_prod.update_layout(
                    **CHART_LAYOUT,
                    height=500,
                    coloraxis_colorbar=dict(title="Margin%"),
                )
                st.plotly_chart(fig_prod, use_container_width=True)
        except Exception as e:
            st.error(f"Lỗi top products: {e}")

    # ── Revenue by Category ──
    with col_cat:
        st.markdown('<div class="section-header">📂 Doanh Thu theo Danh Mục</div>', unsafe_allow_html=True)
        cat_sql = f"""
        SELECT
            dp.category_name,
            SUM(fpd.revenue) AS revenue,
            SUM(fpd.gross_profit) AS profit,
            SUM(fpd.quantity_sold) AS qty
        FROM fact_product_daily fpd
        JOIN dim_product dp ON fpd.product_key = dp.product_key
        JOIN dim_date d     ON fpd.date_key    = d.date_key
        WHERE dp.is_current = TRUE
          {year_filter_date()}
        GROUP BY dp.category_name
        ORDER BY revenue DESC
        """
        try:
            cat_df = run_query(cat_sql)
            if not cat_df.empty:
                fig_cat = px.pie(
                    cat_df, values="revenue", names="category_name",
                    hole=0.45,
                    color_discrete_sequence=COLOR_SEQ,
                )
                fig_cat.update_traces(textposition="outside", textinfo="percent+label")
                fig_cat.update_layout(**CHART_LAYOUT, height=300)
                st.plotly_chart(fig_cat, use_container_width=True)

                # Subcategory breakdown
                fig_cat2 = px.bar(
                    cat_df, x="category_name", y=["revenue", "profit"],
                    barmode="group",
                    color_discrete_map={"revenue": COLOR_BLUE, "profit": COLOR_GREEN},
                    text_auto=".2s",
                )
                fig_cat2.update_layout(**CHART_LAYOUT, height=220, showlegend=True)
                st.plotly_chart(fig_cat2, use_container_width=True)
        except Exception as e:
            st.error(f"Lỗi category: {e}")

    # ── Subcategory Heatmap ──
    st.markdown('<div class="section-header">🗓️ Revenue Heatmap: Subcategory × Quý</div>', unsafe_allow_html=True)
    heat_sql = f"""
    SELECT
        dp.subcategory_name,
        d.year || '-Q' || d.quarter AS period,
        SUM(fpd.revenue) AS revenue
    FROM fact_product_daily fpd
    JOIN dim_product dp ON fpd.product_key = dp.product_key
    JOIN dim_date d     ON fpd.date_key    = d.date_key
    WHERE dp.is_current = TRUE
      {year_filter_date()}
    GROUP BY dp.subcategory_name, d.year, d.quarter
    ORDER BY d.year, d.quarter
    """
    try:
        heat_df = run_query(heat_sql)
        if not heat_df.empty and heat_df["subcategory_name"].nunique() > 1:
            heat_pivot = heat_df.pivot_table(
                index="subcategory_name",
                columns="period",
                values="revenue",
                aggfunc="sum",
                fill_value=0,
            )
            fig_heat = px.imshow(
                heat_pivot,
                color_continuous_scale="Viridis",
                aspect="auto",
                text_auto=".2s",
            )
            fig_heat.update_layout(**CHART_LAYOUT, height=420, xaxis_title="Period", yaxis_title="Subcategory")
            st.plotly_chart(fig_heat, use_container_width=True)
        else:
            st.info("Dữ liệu heatmap chưa đủ để hiển thị.")
    except Exception as e:
        st.error(f"Lỗi heatmap: {e}")

    # ── Inventory Table ──
    st.markdown('<div class="section-header">🏭 Tồn Kho Hiện Tại</div>', unsafe_allow_html=True)
    inv_sql = """
    SELECT
        dp.product_name,
        dp.category_name,
        dp.subcategory_name,
        fi.location_id,
        fi.quantity,
        fi.shelf,
        fi.bin
    FROM fact_inventory fi
    JOIN dim_product dp ON fi.product_key = dp.product_key
    WHERE dp.is_current = TRUE
    ORDER BY fi.quantity DESC
    LIMIT 50
    """
    try:
        inv_df = run_query(inv_sql)
        if not inv_df.empty:
            st.dataframe(
                inv_df.rename(columns={
                    "product_name": "Sản phẩm",
                    "category_name": "Danh mục",
                    "subcategory_name": "Phân loại",
                    "location_id": "Location",
                    "quantity": "Tồn kho",
                    "shelf": "Kệ",
                    "bin": "Bin",
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Chưa có dữ liệu tồn kho.")
    except Exception as e:
        st.error(f"Lỗi inventory: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<hr style='border-color:#1e293b; margin: 32px 0 12px 0;'>
<div style='text-align:center; color:#334155; font-size:0.78rem;'>
    AdventureWorks OLAP Pipeline · Medallion Architecture (Bronze / Silver / Gold)
    · Apache Spark 3.5 · MinIO · PostgreSQL · Apache Airflow 2.9 · Streamlit
</div>
""", unsafe_allow_html=True)
