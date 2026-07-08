"""
streamlit_business_impact.py

Dashboard phân tích tác động kinh doanh từ KMeans Customer Segmentation.
Tập trung vào: Doanh thu, Churn Risk, Cơ hội tăng trưởng, Hành động khuyến nghị.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(
    page_title="Customer Segmentation — Business Impact",
    page_icon="📊",
    layout="wide",
)

# --------------------------------------------------
# CSS
# --------------------------------------------------
st.markdown("""
<style>
    .kpi-card {
        background: #1e293b;
        border-radius: 12px;
        padding: 20px 24px;
        border-left: 4px solid;
        margin-bottom: 8px;
    }
    .kpi-label { color: #94a3b8; font-size: 13px; font-weight: 600; letter-spacing: 1px; }
    .kpi-value { color: #f1f5f9; font-size: 28px; font-weight: 700; margin: 4px 0; }
    .kpi-delta { font-size: 12px; }
    .section-title {
        font-size: 18px; font-weight: 700; color: #f1f5f9;
        border-bottom: 2px solid #334155;
        padding-bottom: 8px; margin: 32px 0 16px 0;
    }
    .action-card {
        border-radius: 10px; padding: 14px 18px; margin: 6px 0;
        font-size: 14px; line-height: 1.6;
    }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# Cluster labels & màu sắc (tuỳ chỉnh theo business)
# --------------------------------------------------
CLUSTER_META = {
    0: {"label": "High-Value At-Risk",  "color": "#f97316", "icon": "⚠️"},   # chi nhiều nhưng lâu không mua
    1: {"label": "Lost Customers",      "color": "#94a3b8", "icon": "💤"},   # tệ nhất mọi mặt
    2: {"label": "Loyal Regulars",      "color": "#22c55e", "icon": "💚"},   # mua thường xuyên, gần đây
    3: {"label": "Champions",           "color": "#f59e0b", "icon": "👑"},   # tốt nhất: spend cao, orders cao, AOV cao
    4: {"label": "New / Promising",     "color": "#3b82f6", "icon": "🆕"},   # mới mua nhất, chưa rõ tiềm năng
}

ACTION_MAP = {
    0: ("Win-back khẩn cấp",     "Từng chi lớn nhưng đang rời đi — gửi offer cá nhân hoá, voucher độc quyền"),
    1: ("Sunset hoặc Last-chance","1 email cuối với discount mạnh, nếu không phản hồi → loại khỏi remarketing"),
    2: ("Upsell & Cross-sell",   "Mua đều nhưng AOV thấp — bundle offer, khuyến khích mua sản phẩm cao hơn"),
    3: ("Giữ chân & Reward",     "Nhóm tốt nhất — loyalty program, early access, ưu tiên CSKH"),
    4: ("Nurture & Convert",     "Vừa mua lần đầu — onboarding email, hướng dẫn sản phẩm, discount lần 2"),
}

# --------------------------------------------------
# Load data
# --------------------------------------------------
@st.cache_data(ttl=600)
def load_data():
    return pd.read_parquet(
        "s3://gold/customer_segments/",
        storage_options={
            "key": "admin",
            "secret": "adminpassword",
            "client_kwargs": {"endpoint_url": "http://minio:9000"}
        }
    )

    rows = []
    for i, c in enumerate(cluster_arr):
        sp = specs[c]
        rows.append({
            "CustomerID": f"C{10000+i}",
            "cluster": int(c),
            "TotalOrders":   max(1, int(np.random.normal(*sp["orders"]))),
            "TotalSpent":    max(0, round(np.random.normal(*sp["spent"]), 2)),
            "AvgOrderValue": max(0, round(np.random.normal(*sp["aov"]), 2)),
            "RecencyDays":   max(1, int(np.random.normal(*sp["recency"]))),
            "AvgDiscount":   max(0, round(np.random.normal(*sp["discount"]), 3)),
            "TerritoryName": np.random.choice(["North", "South", "East", "West", "Central"]),
        })
    return pd.DataFrame(rows)

df_full = load_data()

# Gán label
df_full["ClusterLabel"] = df_full["cluster"].map(lambda x: CLUSTER_META[x]["label"])
df_full["ClusterIcon"]  = df_full["cluster"].map(lambda x: CLUSTER_META[x]["icon"])
COLORS = {CLUSTER_META[k]["label"]: CLUSTER_META[k]["color"] for k in CLUSTER_META}

# --------------------------------------------------
# Sidebar
# --------------------------------------------------
st.sidebar.image("https://img.icons8.com/fluency/96/people-working-together.png", width=60)
st.sidebar.title("Bộ lọc")

selected_clusters = st.sidebar.multiselect(
    "Phân khúc khách hàng",
    options=[CLUSTER_META[k]["label"] for k in sorted(CLUSTER_META)],
    default=[CLUSTER_META[k]["label"] for k in sorted(CLUSTER_META)],
)
selected_territories = st.sidebar.multiselect(
    "Khu vực",
    options=sorted(df_full["TerritoryName"].unique()),
    default=sorted(df_full["TerritoryName"].unique()),
)

df = df_full[
    df_full["ClusterLabel"].isin(selected_clusters) &
    df_full["TerritoryName"].isin(selected_territories)
].copy()

# --------------------------------------------------
# HEADER
# --------------------------------------------------
st.title("📊 Customer Segmentation — Business Impact")
st.caption("Phân tích tác động kinh doanh từ mô hình KMeans · Dữ liệu: gold/customer_segments/")

# ==================================================
# SECTION 1 — EXECUTIVE KPIs
# ==================================================
st.markdown('<div class="section-title">1 · Executive KPIs</div>', unsafe_allow_html=True)

total_revenue   = df["TotalSpent"].sum()
total_customers = len(df)
avg_aov         = df["AvgOrderValue"].mean()
churn_risk_pct  = len(df[df["ClusterLabel"] == "At-Risk"]) / max(len(df), 1) * 100
high_val_rev    = df[df["ClusterLabel"] == "Champions"]["TotalSpent"].sum()
high_val_pct    = high_val_rev / max(total_revenue, 1) * 100

k1, k2, k3, k4, k5 = st.columns(5)
kpis = [
    (k1, "💰 Tổng doanh thu",   f"${total_revenue:,.0f}",  "#22c55e"),
    (k2, "👥 Khách hàng",       f"{total_customers:,}",     "#3b82f6"),
    (k3, "🛒 AOV trung bình",   f"${avg_aov:,.0f}",         "#a855f7"),
    (k4, "⚠️ Churn Risk",       f"{churn_risk_pct:.1f}%",   "#ef4444"),
    (k5, "👑 Rev từ Champions", f"{high_val_pct:.1f}%",      "#f59e0b"),
]
for col, label, value, color in kpis:
    col.markdown(f"""
        <div class="kpi-card" style="border-color:{color}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>""", unsafe_allow_html=True)

# ==================================================
# SECTION 2 — REVENUE IMPACT
# ==================================================
st.markdown('<div class="section-title">2 · Đóng góp doanh thu theo phân khúc</div>', unsafe_allow_html=True)

rev_by_cluster = (
    df.groupby("ClusterLabel")
    .agg(Revenue=("TotalSpent","sum"), Customers=("CustomerID","count"))
    .reset_index()
)
rev_by_cluster["RevPerCustomer"] = rev_by_cluster["Revenue"] / rev_by_cluster["Customers"]
rev_by_cluster["RevShare%"] = rev_by_cluster["Revenue"] / rev_by_cluster["Revenue"].sum() * 100

col_pie, col_bar = st.columns([1, 1.6])

with col_pie:
    fig_pie = px.pie(
        rev_by_cluster,
        names="ClusterLabel",
        values="Revenue",
        color="ClusterLabel",
        color_discrete_map=COLORS,
        hole=0.55,
        title="Tỉ trọng doanh thu (%)",
    )

    fig_pie.update_traces(
        textposition="outside",
        textinfo="percent+label",
        textfont=dict(color="black", size=13)
    )

    fig_pie.update_layout(
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="black",
        title_font_size=15,
        title_font_color="black",
    )

    st.plotly_chart(fig_pie, use_container_width=True)

with col_bar:
    fig_rev = px.bar(
        rev_by_cluster.sort_values("Revenue", ascending=True),
        x="Revenue", y="ClusterLabel",
        color="ClusterLabel", color_discrete_map=COLORS,
        orientation="h",
        text=rev_by_cluster.sort_values("Revenue")["Revenue"].map(lambda x: f"${x:,.0f}"),
        title="Tổng doanh thu & Revenue-per-Customer",
    )
    fig_rev.update_traces(textposition="outside")

    # Overlay RPС line
    fig_rev.add_trace(go.Scatter(
        x=rev_by_cluster.sort_values("Revenue")["RevPerCustomer"],
        y=rev_by_cluster.sort_values("Revenue")["ClusterLabel"],
        mode="markers+text",
        name="Rev/Customer",
        marker=dict(symbol="diamond", size=14, color="#f59e0b",
                    line=dict(color="white", width=2)),
        text=rev_by_cluster.sort_values("Revenue")["RevPerCustomer"].map(lambda x: f"${x:,.0f}"),
        textposition="middle right",
        xaxis="x2",
    ))
    fig_rev.update_layout(
        xaxis2=dict(overlaying="x", side="top", showgrid=False,
                    title="Rev / Customer ($)", title_font_color="#f59e0b"),
        xaxis=dict(title="Tổng doanh thu ($)"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#f1f5f9", title_font_size=15,
        legend=dict(orientation="h", y=-0.15),
        showlegend=False,
        margin=dict(r=100),
    )
    st.plotly_chart(fig_rev, use_container_width=True)

# ==================================================
# SECTION 3 — CHURN RISK & RECENCY
# ==================================================
st.markdown('<div class="section-title">3 · Phân tích Churn Risk</div>', unsafe_allow_html=True)

col_box, col_scatter = st.columns(2)

with col_box:
    fig_box = px.box(
        df, x="ClusterLabel", y="RecencyDays",
        color="ClusterLabel", color_discrete_map=COLORS,
        title="Phân phối RecencyDays theo phân khúc",
        points="outliers",
    )
    fig_box.add_hline(y=90, line_dash="dash", line_color="#f59e0b",
                      annotation_text="Ngưỡng risk 90 ngày",
                      annotation_position="top right")
    fig_box.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#f1f5f9", title_font_size=15, showlegend=False,
    )
    st.plotly_chart(fig_box, use_container_width=True)

with col_scatter:
    # Revenue at risk = khách có recency cao + spending cao
    df["RevenueAtRisk"] = np.where(df["RecencyDays"] > 90, df["TotalSpent"], 0)
    risk_summary = (
        df.groupby("ClusterLabel")
        .agg(RevenueAtRisk=("RevenueAtRisk","sum"), TotalCustomers=("CustomerID","count"))
        .reset_index()
    )
    risk_summary["AtRiskCustomers"] = df[df["RecencyDays"] > 90].groupby("ClusterLabel").size().reindex(risk_summary["ClusterLabel"]).fillna(0).values

    fig_risk = px.scatter(
        risk_summary,
        x="AtRiskCustomers", y="RevenueAtRisk",
        size="TotalCustomers", color="ClusterLabel",
        color_discrete_map=COLORS, text="ClusterLabel",
        title="💸 Doanh thu đang rủi ro (Recency > 90 ngày)",
        size_max=60,
    )
    fig_risk.update_traces(textposition="top center")
    fig_risk.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#f1f5f9", title_font_size=15, showlegend=False,
        xaxis_title="Số KH không hoạt động",
        yaxis_title="Doanh thu đang rủi ro ($)",
    )
    st.plotly_chart(fig_risk, use_container_width=True)

# ==================================================
# SECTION 4 — CLUSTER PROFILING RADAR
# ==================================================
st.markdown('<div class="section-title">4 · DNA từng phân khúc (Radar Chart)</div>', unsafe_allow_html=True)

profile_cols = ["TotalOrders", "TotalSpent", "AvgOrderValue", "RecencyDays", "AvgDiscount"]
profile = df.groupby("ClusterLabel")[profile_cols].mean()

# Chuẩn hoá 0–1 để so sánh các chỉ số có đơn vị khác nhau trên cùng 1 biểu đồ
profile_norm = (profile - profile.min()) / (profile.max() - profile.min() + 1e-9)
# Recency: đảo ngược chiều (recency thấp = tốt/trung thành, nên "Loyalty" = 1 - recency đã chuẩn hoá)
profile_norm["RecencyDays"] = 1 - profile_norm["RecencyDays"]

radar_labels = ["Orders", "Spending", "AOV", "Loyalty (1-Recency)", "Discount"]

col_radar, col_table = st.columns([1.4, 1])

with col_radar:
    fig_radar = go.Figure()
    for cluster_label in profile_norm.index:
        vals = profile_norm.loc[cluster_label, profile_cols].tolist()
        fig_radar.add_trace(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=radar_labels + [radar_labels[0]],
            fill="toself",
            name=cluster_label,
            line_color=COLORS.get(cluster_label, "#888"),
            fillcolor=COLORS.get(cluster_label, "#888"),
            opacity=0.35,
        ))
    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1], color="#475569"),
            angularaxis=dict(color="#94a3b8"),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)", font_color="#f1f5f9",
        legend=dict(orientation="h", y=-0.15),
        title="Đặc trưng phân khúc (chuẩn hoá 0–1)",
        title_font_size=15,
        height=450,
    )
    st.plotly_chart(fig_radar, use_container_width=True)

with col_table:
    st.markdown("**Giá trị trung bình gốc (chưa chuẩn hoá)**")
    raw_display = profile.copy()
    raw_display["TotalSpent"]    = raw_display["TotalSpent"].map("${:,.0f}".format)
    raw_display["AvgOrderValue"] = raw_display["AvgOrderValue"].map("${:,.0f}".format)
    raw_display["TotalOrders"]   = raw_display["TotalOrders"].map("{:.1f}".format)
    raw_display["RecencyDays"]  = raw_display["RecencyDays"].map("{:.0f} ngày".format)
    raw_display["AvgDiscount"]   = raw_display["AvgDiscount"].map("{:.1%}".format)
    raw_display = raw_display.rename(columns={
        "TotalOrders": "Orders TB", "TotalSpent": "Chi tiêu TB",
        "AvgOrderValue": "AOV TB", "RecencyDays": "Recency TB",
        "AvgDiscount": "Discount TB",
    })
    st.dataframe(raw_display, use_container_width=True, height=420)

# ==================================================
# SECTION 5 — GROWTH OPPORTUNITY MATRIX (2×2)
# ==================================================
st.markdown('<div class="section-title">5 · Ma trận cơ hội tăng trưởng</div>', unsafe_allow_html=True)

opp = df.groupby("ClusterLabel").agg(
    AvgSpent=("TotalSpent","mean"),
    AvgRecency=("RecencyDays","mean"),
    Count=("CustomerID","count"),
    TotalRevenue=("TotalSpent","sum"),
).reset_index()

fig_matrix = px.scatter(
    opp,
    x="AvgRecency", y="AvgSpent",
    size="TotalRevenue", color="ClusterLabel",
    color_discrete_map=COLORS,
    text="ClusterLabel",
    size_max=80,
    title="🎯 Spending vs Recency — Cơ hội & Rủi ro",
)
fig_matrix.update_traces(textposition="top center", marker_opacity=0.8)

# Quadrant lines
mid_x = opp["AvgRecency"].mean()
mid_y = opp["AvgSpent"].mean()

fig_matrix.add_vline(x=mid_x, line_dash="dot", line_color="#475569")
fig_matrix.add_hline(y=mid_y, line_dash="dot", line_color="#475569")

# Quadrant labels
for txt, x, y in [
    ("🌟 High Value\nActive",      mid_x*0.4, mid_y*1.6),
    ("⚠️ High Value\nAt-Risk",     mid_x*1.6, mid_y*1.6),
    ("🌱 Low Value\nActive",       mid_x*0.4, mid_y*0.4),
    ("💤 Lost\nCustomers",         mid_x*1.6, mid_y*0.4),
]:
    fig_matrix.add_annotation(
        x=x, y=y, text=txt, showarrow=False,
        font=dict(color="#475569", size=11), align="center",
    )

fig_matrix.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font_color="#f1f5f9", title_font_size=15, showlegend=False,
    xaxis_title="Recency trung bình (ngày) — Càng cao càng rủi ro →",
    yaxis_title="Chi tiêu trung bình ($) — Càng cao càng giá trị →",
    height=420,
)
st.plotly_chart(fig_matrix, use_container_width=True)

# ==================================================
# SECTION 6 — TERRITORY BREAKDOWN
# ==================================================
st.markdown('<div class="section-title">6 · Phân bổ phân khúc theo khu vực</div>', unsafe_allow_html=True)

terr = (
    df.groupby(["TerritoryName","ClusterLabel"])["TotalSpent"]
    .sum().reset_index()
    .rename(columns={"TotalSpent":"Revenue"})
)
fig_terr = px.bar(
    terr, x="TerritoryName", y="Revenue",
    color="ClusterLabel", color_discrete_map=COLORS,
    barmode="stack",
    title="Doanh thu theo khu vực & phân khúc",
    text_auto=".2s",
)
fig_terr.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font_color="#f1f5f9", title_font_size=15,
    xaxis_title="Khu vực", yaxis_title="Doanh thu ($)",
    legend_title="Phân khúc",
)
st.plotly_chart(fig_terr, use_container_width=True)

# ==================================================
# SECTION 7 — ACTION PLAN
# ==================================================
st.markdown('<div class="section-title">7 · Kế hoạch hành động theo phân khúc</div>', unsafe_allow_html=True)

action_colors = {"Champions":"#14532d","At-Risk":"#450a0a","Potential Loyals":"#1e3a5f","Lost Customers":"#1e293b"}
border_colors  = {"Champions":"#22c55e","At-Risk":"#ef4444","Potential Loyals":"#3b82f6","Lost Customers":"#94a3b8"}

cols = st.columns(2)
for i, (cluster_id, (action_title, action_desc)) in enumerate(ACTION_MAP.items()):
    meta = CLUSTER_META[cluster_id]
    cluster_df = df[df["cluster"] == cluster_id]
    rev_contrib = cluster_df["TotalSpent"].sum() / max(df["TotalSpent"].sum(), 1) * 100
    n_cust      = len(cluster_df)
    lbl         = meta["label"]

    with cols[i % 2]:
        st.markdown(f"""
        <div class="action-card"
             style="background:{action_colors.get(lbl,'#1e293b')};
                    border-left: 4px solid {border_colors.get(lbl,'#888')}">
            <b style="color:{border_colors.get(lbl,'#888')};font-size:16px">
                {meta['icon']} {lbl}
            </b>
            <div style="color:#94a3b8;font-size:12px;margin:4px 0">
                {n_cust:,} khách · {rev_contrib:.1f}% doanh thu
            </div>
            <div style="color:#f59e0b;font-weight:600;margin-top:8px">🎯 {action_title}</div>
            <div style="color:#cbd5e1;margin-top:4px">{action_desc}</div>
        </div>
        """, unsafe_allow_html=True)

# ==================================================
# SECTION 8 — FINANCIAL SUMMARY TABLE
# ==================================================
st.markdown('<div class="section-title">8 · Bảng tổng hợp tài chính</div>', unsafe_allow_html=True)

summary = df.groupby("ClusterLabel").agg(
    Customers     =("CustomerID",    "count"),
    TotalRevenue  =("TotalSpent",    "sum"),
    AvgSpend      =("TotalSpent",    "mean"),
    AvgOrders     =("TotalOrders",   "mean"),
    AvgAOV        =("AvgOrderValue", "mean"),
    AvgRecency    =("RecencyDays",   "mean"),
    AvgDiscount   =("AvgDiscount",   "mean"),
).reset_index()

summary["Rev Share (%)"]   = (summary["TotalRevenue"] / summary["TotalRevenue"].sum() * 100).round(1)
summary["TotalRevenue"]    = summary["TotalRevenue"].map("${:,.0f}".format)
summary["AvgSpend"]        = summary["AvgSpend"].map("${:,.0f}".format)
summary["AvgAOV"]          = summary["AvgAOV"].map("${:,.0f}".format)
summary["AvgOrders"]       = summary["AvgOrders"].map("{:.1f}".format)
summary["AvgRecency"]      = summary["AvgRecency"].map("{:.0f} ngày".format)
summary["AvgDiscount"]     = summary["AvgDiscount"].map("{:.1%}".format)

summary = summary.rename(columns={
    "ClusterLabel":  "Phân khúc",
    "Customers":     "Khách hàng",
    "TotalRevenue":  "Tổng doanh thu",
    "AvgSpend":      "Avg Spend",
    "AvgOrders":     "Avg Orders",
    "AvgAOV":        "Avg AOV",
    "AvgRecency":    "Avg Recency",
    "AvgDiscount":   "Avg Discount",
})

st.dataframe(
    summary.set_index("Phân khúc"),
    use_container_width=True,
    height=200,
)

# --------------------------------------------------
# Footer
# --------------------------------------------------
st.divider()
st.caption("🔄 Dữ liệu từ `s3a://gold/customer_segments/` · Mô hình KMeans (k=4) · Spark ML")