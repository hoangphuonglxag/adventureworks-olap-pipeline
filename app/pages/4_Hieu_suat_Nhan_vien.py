"""
4_Hieu_suat_Nhan_vien.py — Phân tích Hiệu suất Nhân viên bán
Nguồn: fact_seller_daily · dim_seller (SCD2)
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.db import run_query, get_date_bounds, clear_cache, fmt_num, fmt_pct, db_connection_guard
from utils.helpers import normalize_date_range

st.set_page_config(page_title="Hiệu suất Nhân viên bán", page_icon="🧑‍💼", layout="wide")
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

    date_range = st.date_input("Khoảng thời gian", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    start_date, end_date = normalize_date_range(date_range, min_date, max_date)

    prorate_quota = st.checkbox(
        "Quy đổi quota theo số ngày đã chọn (giả định sales_quota là chỉ tiêu năm)",
        value=False,
    )

params = {"start_date": start_date, "end_date": end_date}

st.title("🧑‍💼 Hiệu suất Nhân viên bán")
st.caption("Nguồn dữ liệu: `fact_seller_daily` · `dim_seller` (SCD2)")

q_sellers = """
    SELECT ds.seller_id, ds.seller_name, ds.commission_pct, ds.sales_quota, ds.bonus,
           ds.sales_ytd, ds.sales_last_year,
           SUM(fsd.revenue)            AS total_revenue,
           SUM(fsd.commission_earned)  AS total_commission,
           SUM(fsd.order_count)        AS total_orders,
           SUM(fsd.quantity_sold)      AS total_quantity,
           SUM(fsd.customer_count)     AS total_customer_visits
    FROM fact_seller_daily fsd
    JOIN dim_seller ds ON fsd.seller_key = ds.seller_key
    JOIN dim_date d ON fsd.date_key = d.date_key
    WHERE d.full_date BETWEEN :start_date AND :end_date
      AND ds.seller_key <> 'UNKNOWN' AND ds.is_current = TRUE
    GROUP BY ds.seller_id, ds.seller_name, ds.commission_pct, ds.sales_quota, ds.bonus,
             ds.sales_ytd, ds.sales_last_year
"""
df_sellers = run_query(q_sellers, params)

period_days = (end_date - start_date).days + 1
if not df_sellers.empty:
    quota_used = df_sellers["sales_quota"] * (period_days / 365) if prorate_quota else df_sellers["sales_quota"]
    df_sellers["quota_used"] = quota_used
    df_sellers["quota_attainment_pct"] = df_sellers["total_revenue"] / df_sellers["quota_used"].replace(0, pd.NA) * 100
    df_sellers["aov"] = df_sellers["total_revenue"] / df_sellers["total_orders"].replace(0, pd.NA)

tab1, tab2, tab3 = st.tabs(["🏆 Leaderboard & Doanh thu", "🎯 Quota Attainment", "📜 Lịch sử Quota/Bonus (SCD2)"])

# ==============================================================================
# TAB 1 — Leaderboard & Doanh thu
# ==============================================================================
with tab1:
    if df_sellers.empty:
        st.info("Không có dữ liệu nhân viên bán trong khoảng thời gian đã chọn.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🧑‍💼 Số nhân viên có doanh số", fmt_num(len(df_sellers)))
        c2.metric("💰 Tổng doanh thu", fmt_num(df_sellers["total_revenue"].sum()))
        c3.metric("💵 Tổng hoa hồng", fmt_num(df_sellers["total_commission"].sum()))
        c4.metric("🧾 Tổng số đơn", fmt_num(df_sellers["total_orders"].sum()))

        top_n = st.slider("Số lượng hiển thị (Top N)", 5, 30, 10, key="seller_top_n")
        lb = df_sellers.nlargest(top_n, "total_revenue").sort_values("total_revenue")
        fig_lb = px.bar(
            lb, x="total_revenue", y="seller_name", orientation="h",
            title=f"🏆 Leaderboard — Top {top_n} theo doanh thu",
            color="total_revenue", color_continuous_scale="Tealgrn",
            hover_data={"total_orders": True, "total_commission": True},
        )
        fig_lb.update_layout(height=max(350, 28 * top_n), coloraxis_showscale=False)
        st.plotly_chart(fig_lb, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            fig_orders = px.bar(
                df_sellers.nlargest(top_n, "total_orders").sort_values("total_orders"),
                x="total_orders", y="seller_name", orientation="h",
                title=f"Top {top_n} theo số đơn hàng", color_discrete_sequence=["#6366f1"],
            )
            st.plotly_chart(fig_orders, use_container_width=True)
        with c2:
            fig_comm = px.bar(
                df_sellers.nlargest(top_n, "total_commission").sort_values("total_commission"),
                x="total_commission", y="seller_name", orientation="h",
                title=f"Top {top_n} theo hoa hồng", color_discrete_sequence=["#f59e0b"],
            )
            st.plotly_chart(fig_comm, use_container_width=True)

        with st.expander("📋 Bảng chi tiết toàn bộ nhân viên"):
            show = df_sellers[["seller_name", "total_revenue", "total_orders", "aov", "total_quantity", "total_commission", "commission_pct"]].copy()
            show.columns = ["Nhân viên", "Doanh thu", "Số đơn", "AOV", "Số lượng bán", "Hoa hồng", "% Hoa hồng"]
            st.dataframe(
                show.sort_values("Doanh thu", ascending=False).style.format(
                    {"Doanh thu": "{:,.0f}", "AOV": "{:,.0f}", "Số lượng bán": "{:,.0f}", "Hoa hồng": "{:,.0f}", "% Hoa hồng": "{:,.2f}%"}
                ),
                use_container_width=True, hide_index=True, height=400,
            )

# ==============================================================================
# TAB 2 — Quota Attainment
# ==============================================================================
with tab2:
    if df_sellers.empty:
        st.info("Không có dữ liệu trong khoảng thời gian đã chọn.")
    else:
        if prorate_quota:
            st.caption(f"📐 Quota đang được quy đổi theo {period_days} ngày đã chọn (giả định `sales_quota` là chỉ tiêu năm).")
        else:
            st.caption("📐 Đang so sánh trực tiếp doanh thu kỳ đã chọn với `sales_quota` (không quy đổi theo số ngày).")

        avg_attainment = df_sellers["quota_attainment_pct"].mean()
        over_quota = (df_sellers["quota_attainment_pct"] >= 100).sum()
        c1, c2 = st.columns(2)
        c1.metric("📊 Tỷ lệ đạt quota TB", fmt_pct(avg_attainment))
        c2.metric("✅ Số nhân viên đạt/vượt quota", f"{over_quota}/{len(df_sellers)}")

        fig_att = px.bar(
            df_sellers.sort_values("quota_attainment_pct"), x="quota_attainment_pct", y="seller_name", orientation="h",
            title="Tỷ lệ đạt quota theo nhân viên (%)",
            color="quota_attainment_pct", color_continuous_scale=["#ef4444", "#f59e0b", "#10b981"],
        )
        fig_att.add_vline(x=100, line_dash="dash", line_color="gray")
        fig_att.update_layout(height=max(350, 22 * len(df_sellers)), coloraxis_showscale=False)
        st.plotly_chart(fig_att, use_container_width=True)

        st.divider()
        st.markdown("**So sánh với `sales_ytd` / `sales_last_year` (snapshot từ hệ thống nguồn)**")
        comp = df_sellers[["seller_name", "total_revenue", "sales_ytd", "sales_last_year"]].copy()
        comp.columns = ["Nhân viên", "Doanh thu (kỳ đã lọc)", "Sales YTD (nguồn)", "Sales năm trước (nguồn)"]
        st.dataframe(
            comp.style.format({"Doanh thu (kỳ đã lọc)": "{:,.0f}", "Sales YTD (nguồn)": "{:,.0f}", "Sales năm trước (nguồn)": "{:,.0f}"}),
            use_container_width=True, hide_index=True,
        )

# ==============================================================================
# TAB 3 — Lịch sử Quota / Bonus (SCD2)
# ==============================================================================
with tab3:
    q_seller_names = "SELECT DISTINCT seller_id, seller_name FROM dim_seller WHERE seller_id <> -1 ORDER BY seller_name"
    df_seller_names = run_query(q_seller_names)

    if df_seller_names.empty:
        st.info("Chưa có dữ liệu nhân viên bán.")
    else:
        selected_seller = st.selectbox("Chọn nhân viên", df_seller_names["seller_name"].tolist())
        seller_id = int(df_seller_names.loc[df_seller_names["seller_name"] == selected_seller, "seller_id"].iloc[0])

        q_history = """
            SELECT version, effective_date, expiry_date, is_current,
                   commission_pct, sales_quota, bonus, sales_ytd, sales_last_year
            FROM dim_seller
            WHERE seller_id = :seller_id
            ORDER BY version
        """
        df_hist = run_query(q_history, {"seller_id": seller_id})

        if df_hist.empty:
            st.info("Không có lịch sử cho nhân viên này.")
        else:
            if len(df_hist) == 1:
                st.info(f"**{selected_seller}** chưa có thay đổi nào về quota/bonus (chỉ có 1 phiên bản).")
            else:
                fig_hist = px.line(
                    df_hist, x="effective_date", y=["sales_quota", "bonus"], markers=True,
                    title=f"Lịch sử Quota & Bonus — {selected_seller}",
                    labels={"value": "Giá trị", "effective_date": "Hiệu lực từ", "variable": "Chỉ tiêu"},
                )
                st.plotly_chart(fig_hist, use_container_width=True)

            show_hist = df_hist.copy()
            show_hist.columns = ["Phiên bản", "Hiệu lực từ", "Hết hiệu lực", "Đang dùng", "% Hoa hồng", "Quota", "Bonus", "Sales YTD", "Sales năm trước"]
            st.dataframe(
                show_hist.style.format({"Quota": "{:,.0f}", "Bonus": "{:,.0f}", "Sales YTD": "{:,.0f}", "Sales năm trước": "{:,.0f}", "% Hoa hồng": "{:,.2f}%"}),
                use_container_width=True, hide_index=True,
            )

# ==============================================================================
# Gợi ý SQL
# ==============================================================================
with st.expander("🧠 Gợi ý SQL"):
    st.code(
        """SELECT ds.seller_name, SUM(fsd.revenue) AS total_revenue,
       SUM(fsd.commission_earned) AS total_commission
FROM fact_seller_daily fsd
JOIN dim_seller ds ON fsd.seller_key = ds.seller_key
JOIN dim_date d ON fsd.date_key = d.date_key
WHERE d.full_date BETWEEN :start_date AND :end_date
  AND ds.seller_key <> 'UNKNOWN' AND ds.is_current = TRUE
GROUP BY ds.seller_name
ORDER BY total_revenue DESC;""",
        language="sql",
    )
    st.markdown(
        "**Lưu ý:** `seller_key = 'UNKNOWN'` là dòng đại diện cho đơn hàng Online không có "
        "nhân viên bán (`SalesPersonID` rỗng) — đã loại trừ khỏi các phân tích hiệu suất cá nhân ở trang này."
    )
