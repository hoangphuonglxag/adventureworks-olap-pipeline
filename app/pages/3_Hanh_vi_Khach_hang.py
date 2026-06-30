"""
3_Hanh_vi_Khach_hang.py — Phân tích Hành vi Khách hàng
Nguồn: fact_customer_behavior · dim_customer (SCD2) · fact_order (cho cohort/khoảng cách mua hàng)
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.db import run_query, get_date_bounds, clear_cache, fmt_num, fmt_pct, safe_div, db_connection_guard
from utils.helpers import normalize_date_range

st.set_page_config(page_title="Hành vi Khách hàng", page_icon="👥", layout="wide")
db_connection_guard()

with st.sidebar:
    st.header("⚙️ Bộ lọc")
    if st.button("🔄 Làm mới dữ liệu", use_container_width=True):
        clear_cache()
        st.rerun()

    min_date, max_date = get_date_bounds()
    if min_date is None:
        st.warning("Chưa có dữ liệu.")
        st.stop()

    date_range = st.date_input(
        "Khoảng thời gian (áp dụng cho phân tích khoảng cách mua & cohort)",
        value=(min_date, max_date), min_value=min_date, max_value=max_date,
    )
    start_date, end_date = normalize_date_range(date_range, min_date, max_date)

params = {"start_date": start_date, "end_date": end_date}

st.title("👥 Hành vi Khách hàng")
st.caption("Nguồn dữ liệu: `fact_customer_behavior` · `dim_customer` (SCD2)")

# ----------------------------------------------------------------------------
# Dữ liệu RFM gốc — fact_customer_behavior đã là bảng snapshot trọn đời khách hàng
# ----------------------------------------------------------------------------
q_rfm = """
    SELECT dc.customer_id, dc.customer_name, dc.customer_type,
           fcb.total_orders, fcb.total_quantity, fcb.total_amount, fcb.avg_order_value,
           fcb.first_purchase, fcb.last_purchase, fcb.recency_days, fcb.customer_segment
    FROM fact_customer_behavior fcb
    JOIN dim_customer dc ON fcb.customer_key = dc.customer_key
    WHERE dc.is_current = TRUE AND dc.customer_key <> 'UNKNOWN'
"""
df_rfm = run_query(q_rfm)

tab1, tab2, tab3, tab4 = st.tabs(
    ["🎯 RFM & Phân khúc", "💎 Customer Lifetime Value", "🔁 Giữ chân & Cohort", "⏱️ Khoảng cách mua hàng"]
)

# ==============================================================================
# TAB 1 — RFM & Phân khúc
# ==============================================================================
with tab1:
    if df_rfm.empty:
        st.info("Chưa có dữ liệu khách hàng trong `fact_customer_behavior`.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("👥 Tổng khách hàng", fmt_num(len(df_rfm)))
        c2.metric("💰 Tổng giá trị (Monetary)", fmt_num(df_rfm["total_amount"].sum()))
        c3.metric("🧾 AOV trung bình", fmt_num(df_rfm["avg_order_value"].mean(), 0))
        c4.metric("⏱️ Recency TB (ngày)", fmt_num(df_rfm["recency_days"].mean(), 0))

        st.markdown("**Phân khúc khách hàng hiện có (`customer_segment`)**")
        seg_agg = (
            df_rfm.groupby("customer_segment", as_index=False)
            .agg(customers=("customer_id", "count"), revenue=("total_amount", "sum"), avg_orders=("total_orders", "mean"))
        )
        c1, c2 = st.columns(2)
        with c1:
            fig_seg = px.pie(seg_agg, names="customer_segment", values="customers", hole=0.45, title="Số lượng khách theo phân khúc")
            st.plotly_chart(fig_seg, use_container_width=True)
        with c2:
            fig_seg_rev = px.bar(
                seg_agg.sort_values("revenue"), x="revenue", y="customer_segment", orientation="h",
                title="Doanh thu theo phân khúc", color_discrete_sequence=["#6366f1"],
            )
            st.plotly_chart(fig_seg_rev, use_container_width=True)

        st.divider()
        st.markdown("**Phân tích RFM chi tiết (tính điểm ngũ phân vị 1–5)**")
        st.caption("R = Recency (mới mua gần đây), F = Frequency (`total_orders`), M = Monetary (`total_amount`)")

        try:
            rfm = df_rfm.copy()
            rfm["R_score"] = pd.qcut(rfm["recency_days"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
            rfm["F_score"] = pd.qcut(rfm["total_orders"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
            rfm["M_score"] = pd.qcut(rfm["total_amount"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
            rfm["RFM_score"] = rfm["R_score"] + rfm["F_score"] + rfm["M_score"]

            def label_segment(score):
                if score >= 13:
                    return "🏆 Champions"
                if score >= 10:
                    return "💚 Loyal"
                if score >= 7:
                    return "🟡 Potential"
                if score >= 4:
                    return "🟠 At Risk"
                return "🔴 Lost"

            rfm["RFM_segment"] = rfm["RFM_score"].apply(label_segment)

            fig_rfm_scatter = px.scatter(
                rfm, x="recency_days", y="total_amount", size="total_orders", color="RFM_segment",
                hover_name="customer_name", title="Recency vs Monetary (kích thước = số đơn hàng)",
                labels={"recency_days": "Recency (ngày)", "total_amount": "Monetary"},
            )
            st.plotly_chart(fig_rfm_scatter, use_container_width=True)

            rfm_seg_agg = rfm.groupby("RFM_segment", as_index=False).agg(
                customers=("customer_id", "count"), revenue=("total_amount", "sum")
            )
            fig_rfm_seg = px.bar(
                rfm_seg_agg.sort_values("customers"), x="customers", y="RFM_segment", orientation="h",
                title="Số khách hàng theo phân khúc RFM tính toán", color_discrete_sequence=["#10b981"],
            )
            st.plotly_chart(fig_rfm_seg, use_container_width=True)

            with st.expander("📋 Bảng chi tiết RFM theo khách hàng"):
                show_rfm = rfm[["customer_name", "recency_days", "total_orders", "total_amount", "R_score", "F_score", "M_score", "RFM_score", "RFM_segment"]]
                st.dataframe(show_rfm.sort_values("RFM_score", ascending=False), use_container_width=True, hide_index=True, height=400)
        except ValueError:
            st.info("Không đủ dữ liệu phân tán để chia ngũ phân vị RFM (cần nhiều khách hàng hơn).")

# ==============================================================================
# TAB 2 — Customer Lifetime Value
# ==============================================================================
with tab2:
    if df_rfm.empty:
        st.info("Chưa có dữ liệu khách hàng.")
    else:
        st.markdown("**Ước tính CLV = AOV × Tần suất mua/năm × Vòng đời giả định (năm)**")
        lifespan_years = st.slider("Vòng đời khách hàng giả định (năm)", 1, 10, 3)

        clv = df_rfm.copy()
        clv["first_purchase"] = pd.to_datetime(clv["first_purchase"])
        clv["last_purchase"] = pd.to_datetime(clv["last_purchase"])
        clv["tenure_days"] = (clv["last_purchase"] - clv["first_purchase"]).dt.days.clip(lower=1)
        clv["orders_per_year"] = clv["total_orders"] / (clv["tenure_days"] / 365)
        clv.loc[clv["total_orders"] <= 1, "orders_per_year"] = clv["total_orders"]
        clv["estimated_clv"] = clv["avg_order_value"] * clv["orders_per_year"] * lifespan_years

        c1, c2, c3 = st.columns(3)
        c1.metric("💎 CLV ước tính TB/khách", fmt_num(clv["estimated_clv"].mean(), 0))
        c2.metric("💰 Giá trị đã ghi nhận TB (total_amount)", fmt_num(clv["total_amount"].mean(), 0))
        c3.metric("🔝 CLV cao nhất", fmt_num(clv["estimated_clv"].max(), 0))

        st.caption(
            "ℹ️ Công thức kinh điển CLV = AOV × Tần suất mua hàng/năm × Vòng đời khách hàng. "
            "Đây là **ước tính**, không phải số liệu lịch sử thực tế — dùng để so sánh tương đối giữa các khách hàng."
        )

        fig_clv = px.histogram(clv, x="estimated_clv", nbins=30, title="Phân phối CLV ước tính", color_discrete_sequence=["#a855f7"])
        st.plotly_chart(fig_clv, use_container_width=True)

        st.markdown("**Top 20 khách hàng theo CLV ước tính**")
        top_clv = clv.nlargest(20, "estimated_clv")[["customer_name", "customer_type", "total_orders", "avg_order_value", "tenure_days", "estimated_clv", "total_amount"]]
        top_clv.columns = ["Khách hàng", "Loại KH", "Số đơn", "AOV", "Tenure (ngày)", "CLV ước tính", "Giá trị đã ghi nhận"]
        st.dataframe(
            top_clv.style.format({"AOV": "{:,.0f}", "CLV ước tính": "{:,.0f}", "Giá trị đã ghi nhận": "{:,.0f}"}),
            use_container_width=True, hide_index=True,
        )

# ==============================================================================
# TAB 3 — Giữ chân & Cohort
# ==============================================================================
with tab3:
    repeat_rate = safe_div((df_rfm["total_orders"] > 1).sum(), len(df_rfm)) if not df_rfm.empty else None
    c1, c2 = st.columns(2)
    c1.metric("🔁 Tỷ lệ khách mua lại (>1 đơn)", fmt_pct(repeat_rate * 100 if repeat_rate is not None else None))
    c2.metric("🆕 Khách chỉ mua 1 lần", fmt_num((df_rfm["total_orders"] == 1).sum()) if not df_rfm.empty else "—")

    st.divider()
    st.markdown("**Cohort Retention theo tháng mua hàng đầu tiên**")
    st.caption(
        f"Dựa trên đơn hàng trong khoảng {start_date:%d/%m/%Y} → {end_date:%d/%m/%Y} đã chọn ở sidebar. "
        "Cohort = tháng phát sinh đơn hàng đầu tiên của khách (trong khoảng lọc)."
    )

    q_orders = """
        SELECT DISTINCT fo.order_id, fo.customer_key, d.full_date
        FROM fact_order fo
        JOIN dim_date d ON fo.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
          AND fo.customer_key <> 'UNKNOWN'
    """
    df_orders = run_query(q_orders, params)

    if df_orders.empty:
        st.info("Không có dữ liệu đơn hàng trong khoảng thời gian đã chọn.")
    else:
        df_orders["full_date"] = pd.to_datetime(df_orders["full_date"])
        df_orders["order_month"] = df_orders["full_date"].values.astype("datetime64[M]")
        cohort_month = df_orders.groupby("customer_key")["order_month"].min().rename("cohort_month")
        df_orders = df_orders.join(cohort_month, on="customer_key")
        df_orders["cohort_index"] = (
            (df_orders["order_month"].dt.year - df_orders["cohort_month"].dt.year) * 12
            + (df_orders["order_month"].dt.month - df_orders["cohort_month"].dt.month)
        )

        cohort_data = (
            df_orders.groupby(["cohort_month", "cohort_index"])["customer_key"].nunique().reset_index()
        )
        cohort_pivot = cohort_data.pivot(index="cohort_month", columns="cohort_index", values="customer_key")
        cohort_size = cohort_pivot[0]
        retention = cohort_pivot.divide(cohort_size, axis=0) * 100

        retention.index = retention.index.strftime("%m/%Y")
        if retention.shape[1] > 1:
            fig_cohort = px.imshow(
                retention, text_auto=".0f", aspect="auto", color_continuous_scale="Blues",
                labels=dict(x="Tháng kể từ lần mua đầu (cohort index)", y="Cohort (tháng mua đầu tiên)", color="% giữ chân"),
                title="Ma trận Cohort Retention (%)",
            )
            fig_cohort.update_layout(height=450)
            st.plotly_chart(fig_cohort, use_container_width=True)
        else:
            st.info("Khoảng thời gian đã chọn quá ngắn để dựng ma trận cohort (cần dữ liệu trải dài nhiều tháng).")

# ==============================================================================
# TAB 4 — Khoảng cách giữa các lần mua hàng
# ==============================================================================
with tab4:
    q_orders2 = """
        SELECT DISTINCT fo.order_id, fo.customer_key, d.full_date
        FROM fact_order fo
        JOIN dim_date d ON fo.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
          AND fo.customer_key <> 'UNKNOWN'
    """
    df_o2 = run_query(q_orders2, params)

    if df_o2.empty:
        st.info("Không có dữ liệu đơn hàng trong khoảng thời gian đã chọn.")
    else:
        df_o2["full_date"] = pd.to_datetime(df_o2["full_date"])
        df_o2 = df_o2.sort_values(["customer_key", "full_date"])
        df_o2["days_since_prev"] = df_o2.groupby("customer_key")["full_date"].diff().dt.days

        intervals = df_o2.dropna(subset=["days_since_prev"])
        if intervals.empty:
            st.info("Chưa có khách hàng nào mua từ 2 đơn trở lên trong khoảng thời gian đã chọn.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("⏱️ Khoảng cách mua TB", fmt_num(intervals["days_since_prev"].mean(), 1, " ngày"))
            c2.metric("📊 Trung vị", fmt_num(intervals["days_since_prev"].median(), 1, " ngày"))
            c3.metric("👥 Số khách có ≥2 đơn", fmt_num(intervals["customer_key"].nunique()))

            fig_int = px.histogram(
                intervals, x="days_since_prev", nbins=30,
                title="Phân phối khoảng cách giữa 2 lần mua liên tiếp (ngày)",
                color_discrete_sequence=["#0ea5e9"],
            )
            st.plotly_chart(fig_int, use_container_width=True)

# ==============================================================================
# Gợi ý SQL
# ==============================================================================
with st.expander("🧠 Gợi ý SQL"):
    st.code(
        """SELECT dc.customer_name, fcb.total_orders, fcb.total_amount,
       fcb.recency_days, fcb.customer_segment
FROM fact_customer_behavior fcb
JOIN dim_customer dc ON fcb.customer_key = dc.customer_key
WHERE dc.is_current = TRUE AND dc.customer_key <> 'UNKNOWN';""",
        language="sql",
    )
    st.markdown(
        "`fact_customer_behavior` đã là bảng tổng hợp **trọn đời** mỗi khách hàng (snapshot), "
        "nên RFM/CLV ở đây dùng trực tiếp bảng này. Riêng phân tích Cohort & Khoảng cách mua hàng "
        "cần dữ liệu ở **grain đơn hàng** nên truy vấn trực tiếp từ `fact_order` (đã `DISTINCT` theo `order_id`)."
    )
