"""
1_Doanh_thu_Don_hang.py — Phân tích Doanh thu & Đơn hàng
Nguồn: fact_order · fact_order_daily
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import datetime as dt

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.db import run_query, get_date_bounds, clear_cache, fmt_num, fmt_pct, safe_div, db_connection_guard
from utils.helpers import GRANULARITY_OPTIONS, add_period_column, growth_pct, normalize_date_range

st.set_page_config(page_title="Doanh thu & Đơn hàng", page_icon="📈", layout="wide")
db_connection_guard()

# ----------------------------------------------------------------------------
# Sidebar — bộ lọc
# ----------------------------------------------------------------------------
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
        "Khoảng thời gian",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    start_date, end_date = normalize_date_range(date_range, min_date, max_date)

    granularity = st.selectbox("Mức gộp thời gian", GRANULARITY_OPTIONS, index=2)

params = {"start_date": start_date, "end_date": end_date}

st.title("📈 Doanh thu & Đơn hàng")
st.caption("Nguồn dữ liệu: `fact_order` · `fact_order_daily`")

tab1, tab2, tab3, tab4 = st.tabs(
    ["📈 Xu hướng doanh thu & AOV", "🛒 Kênh bán hàng", "💸 Chiết khấu • Thuế • Phí", "📊 Tăng trưởng"]
)

# ==============================================================================
# TAB 1 — Xu hướng doanh thu / đơn hàng / AOV
# ==============================================================================
with tab1:
    q_daily = """
        SELECT d.full_date,
               fod.daily_revenue, fod.daily_order_count,
               fod.daily_quantity, fod.daily_customer_count
        FROM fact_order_daily fod
        JOIN dim_date d ON fod.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
        ORDER BY d.full_date
    """
    df_daily = run_query(q_daily, params)

    if df_daily.empty:
        st.info("Không có dữ liệu trong khoảng thời gian đã chọn.")
    else:
        total_revenue = df_daily["daily_revenue"].sum()
        total_orders = df_daily["daily_order_count"].sum()
        total_qty = df_daily["daily_quantity"].sum()
        aov = safe_div(total_revenue, total_orders)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Tổng doanh thu", fmt_num(total_revenue))
        c2.metric("🧾 Tổng đơn hàng", fmt_num(total_orders))
        c3.metric("📦 Tổng số lượng bán", fmt_num(total_qty))
        c4.metric("🎯 AOV (TB/đơn)", fmt_num(aov, 0))

        dfp = add_period_column(df_daily, "full_date", granularity)
        agg = (
            dfp.groupby(["period", "period_label"], as_index=False)
            .agg(
                revenue=("daily_revenue", "sum"),
                orders=("daily_order_count", "sum"),
                quantity=("daily_quantity", "sum"),
                customer_visits=("daily_customer_count", "sum"),
            )
            .sort_values("period")
        )
        agg["aov"] = agg["revenue"] / agg["orders"].replace(0, pd.NA)

        fig_rev = go.Figure()
        fig_rev.add_bar(x=agg["period_label"], y=agg["revenue"], name="Doanh thu", marker_color="#6366f1")
        fig_rev.add_trace(
            go.Scatter(
                x=agg["period_label"], y=agg["aov"], name="AOV", yaxis="y2",
                mode="lines+markers", line=dict(color="#f59e0b", width=3),
            )
        )
        fig_rev.update_layout(
            title=f"Doanh thu & AOV theo {granularity.lower()}",
            yaxis=dict(title="Doanh thu"),
            yaxis2=dict(title="AOV", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.1),
            height=420,
        )
        st.plotly_chart(fig_rev, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            fig_orders = px.bar(
                agg, x="period_label", y="orders", title=f"Số đơn hàng theo {granularity.lower()}",
                color_discrete_sequence=["#10b981"],
            )
            st.plotly_chart(fig_orders, use_container_width=True)
        with c2:
            fig_qty = px.bar(
                agg, x="period_label", y="quantity", title=f"Số lượng bán theo {granularity.lower()}",
                color_discrete_sequence=["#0ea5e9"],
            )
            st.plotly_chart(fig_qty, use_container_width=True)

        st.caption(
            "ℹ️ *customer_visits* là tổng lượt khách mua theo từng ngày cộng dồn lại "
            "(không phải số khách hàng *duy nhất* trong cả giai đoạn)."
        )

        with st.expander("📋 Xem dữ liệu chi tiết"):
            st.dataframe(agg.drop(columns=["period"]), use_container_width=True, hide_index=True)

# ==============================================================================
# TAB 2 — Kênh bán hàng Online vs Offline
# ==============================================================================
with tab2:
    q_channel = """
        SELECT d.full_date, fo.sales_channel,
               SUM(fo.line_total)             AS revenue,
               COUNT(DISTINCT fo.order_id)    AS order_count,
               SUM(fo.order_qty)              AS quantity
        FROM fact_order fo
        JOIN dim_date d ON fo.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
          AND fo.sales_channel IS NOT NULL
        GROUP BY d.full_date, fo.sales_channel
        ORDER BY d.full_date
    """
    df_ch = run_query(q_channel, params)

    if df_ch.empty:
        st.info("Không có dữ liệu kênh bán trong khoảng thời gian đã chọn.")
    else:
        ch_total = (
            df_ch.groupby("sales_channel", as_index=False)
            .agg(revenue=("revenue", "sum"), orders=("order_count", "sum"), quantity=("quantity", "sum"))
        )
        ch_total["aov"] = ch_total["revenue"] / ch_total["orders"].replace(0, pd.NA)
        ch_total["revenue_share"] = ch_total["revenue"] / ch_total["revenue"].sum() * 100

        c1, c2 = st.columns([1, 1.4])
        with c1:
            fig_pie = px.pie(
                ch_total, names="sales_channel", values="revenue", hole=0.45,
                title="Tỷ trọng doanh thu theo kênh",
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            show_cols = ch_total.rename(
                columns={
                    "sales_channel": "Kênh", "revenue": "Doanh thu", "orders": "Số đơn",
                    "quantity": "Số lượng", "aov": "AOV", "revenue_share": "% Doanh thu",
                }
            )
            st.dataframe(
                show_cols.style.format(
                    {"Doanh thu": "{:,.0f}", "Số đơn": "{:,.0f}", "Số lượng": "{:,.0f}",
                     "AOV": "{:,.0f}", "% Doanh thu": "{:,.1f}%"}
                ),
                use_container_width=True, hide_index=True,
            )

        dfp_ch = add_period_column(df_ch, "full_date", granularity)
        agg_ch = (
            dfp_ch.groupby(["period", "period_label", "sales_channel"], as_index=False)["revenue"]
            .sum()
            .sort_values("period")
        )
        fig_trend = px.bar(
            agg_ch, x="period_label", y="revenue", color="sales_channel", barmode="group",
            title=f"Doanh thu theo kênh — {granularity.lower()}",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        st.plotly_chart(fig_trend, use_container_width=True)

# ==============================================================================
# TAB 3 — Chiết khấu, Thuế, Phí vận chuyển
# ==============================================================================
with tab3:
    q_discount = """
        SELECT d.full_date,
               SUM(fo.order_qty * fo.unit_price)                       AS gross_amount,
               SUM(fo.order_qty * fo.unit_price * fo.unit_price_discount) AS discount_amount,
               AVG(fo.unit_price_discount)                              AS avg_discount_rate
        FROM fact_order fo
        JOIN dim_date d ON fo.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
        GROUP BY d.full_date
        ORDER BY d.full_date
    """
    # sub_total / tax_amt / freight_amt / total_due là field cấp HEADER đơn hàng,
    # bị lặp lại trên mỗi dòng line-item → phải DISTINCT theo order_id trước khi SUM,
    # tránh đếm trùng (double-counting).
    q_header = """
        WITH order_header AS (
            SELECT DISTINCT fo.order_id, fo.date_key,
                   fo.sub_total, fo.tax_amt, fo.freight_amt, fo.total_due
            FROM fact_order fo
        )
        SELECT d.full_date,
               SUM(oh.sub_total)    AS sub_total,
               SUM(oh.tax_amt)      AS tax_amt,
               SUM(oh.freight_amt)  AS freight_amt,
               SUM(oh.total_due)    AS total_due
        FROM order_header oh
        JOIN dim_date d ON oh.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
        GROUP BY d.full_date
        ORDER BY d.full_date
    """
    df_disc = run_query(q_discount, params)
    df_head = run_query(q_header, params)

    if df_disc.empty and df_head.empty:
        st.info("Không có dữ liệu trong khoảng thời gian đã chọn.")
    else:
        df_merge = pd.merge(df_disc, df_head, on="full_date", how="outer").fillna(0)

        total_discount = df_merge["discount_amount"].sum()
        total_tax = df_merge["tax_amt"].sum()
        total_freight = df_merge["freight_amt"].sum()
        total_subtotal = df_merge["sub_total"].sum()
        avg_disc_rate = df_disc["avg_discount_rate"].mean() if not df_disc.empty else None

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏷️ Tổng chiết khấu", fmt_num(total_discount))
        c2.metric("📐 Tỷ lệ chiết khấu TB", fmt_pct(avg_disc_rate * 100 if avg_disc_rate is not None else None))
        c3.metric("🧾 Tổng thuế", fmt_num(total_tax), )
        c4.metric("🚚 Tổng phí vận chuyển", fmt_num(total_freight))

        c1, c2 = st.columns(2)
        c1.metric("Thuế / Doanh thu (sub_total)", fmt_pct(safe_div(total_tax, total_subtotal) and safe_div(total_tax, total_subtotal) * 100))
        c2.metric("Phí VC / Doanh thu (sub_total)", fmt_pct(safe_div(total_freight, total_subtotal) and safe_div(total_freight, total_subtotal) * 100))

        dfp_m = add_period_column(df_merge, "full_date", granularity)
        agg_m = (
            dfp_m.groupby(["period", "period_label"], as_index=False)
            .agg(
                discount_amount=("discount_amount", "sum"),
                tax_amt=("tax_amt", "sum"),
                freight_amt=("freight_amt", "sum"),
                sub_total=("sub_total", "sum"),
            )
            .sort_values("period")
        )
        fig_stack = go.Figure()
        fig_stack.add_bar(x=agg_m["period_label"], y=agg_m["discount_amount"], name="Chiết khấu")
        fig_stack.add_bar(x=agg_m["period_label"], y=agg_m["tax_amt"], name="Thuế")
        fig_stack.add_bar(x=agg_m["period_label"], y=agg_m["freight_amt"], name="Phí vận chuyển")
        fig_stack.update_layout(
            barmode="stack", title=f"Chiết khấu / Thuế / Phí vận chuyển theo {granularity.lower()}", height=420,
        )
        st.plotly_chart(fig_stack, use_container_width=True)

        if not df_disc.empty:
            fig_hist = px.histogram(
                df_disc[df_disc["avg_discount_rate"] > 0], x="avg_discount_rate", nbins=20,
                title="Phân phối tỷ lệ chiết khấu trung bình theo ngày",
                color_discrete_sequence=["#a855f7"],
            )
            st.plotly_chart(fig_hist, use_container_width=True)

# ==============================================================================
# TAB 4 — Tăng trưởng & so sánh kỳ
# ==============================================================================
with tab4:
    period_len = (end_date - start_date).days + 1
    prev_end = start_date - dt.timedelta(days=1)
    prev_start = prev_end - dt.timedelta(days=period_len - 1)

    q_compare = """
        SELECT COALESCE(SUM(daily_revenue), 0) AS revenue,
               COALESCE(SUM(daily_order_count), 0) AS orders,
               COALESCE(SUM(daily_quantity), 0) AS quantity
        FROM fact_order_daily fod
        JOIN dim_date d ON fod.date_key = d.date_key
        WHERE d.full_date BETWEEN :p_start AND :p_end
    """
    cur = run_query(q_compare, {"p_start": start_date, "p_end": end_date}).iloc[0]
    prev = run_query(q_compare, {"p_start": prev_start, "p_end": prev_end}).iloc[0]

    cur_aov = safe_div(cur["revenue"], cur["orders"])
    prev_aov = safe_div(prev["revenue"], prev["orders"])

    st.markdown(
        f"**Kỳ hiện tại:** {start_date:%d/%m/%Y} → {end_date:%d/%m/%Y}  ·  "
        f"**Kỳ trước đó ({period_len} ngày):** {prev_start:%d/%m/%Y} → {prev_end:%d/%m/%Y}"
    )

    c1, c2, c3 = st.columns(3)
    g_rev = growth_pct(cur["revenue"], prev["revenue"])
    g_ord = growth_pct(cur["orders"], prev["orders"])
    g_aov = growth_pct(cur_aov, prev_aov) if cur_aov and prev_aov else None
    c1.metric("💰 Doanh thu", fmt_num(cur["revenue"]), fmt_pct(g_rev) if g_rev is not None else None)
    c2.metric("🧾 Số đơn hàng", fmt_num(cur["orders"]), fmt_pct(g_ord) if g_ord is not None else None)
    c3.metric("🎯 AOV", fmt_num(cur_aov, 0), fmt_pct(g_aov) if g_aov is not None else None)

    st.divider()
    st.markdown(f"**Tăng trưởng theo từng {granularity.lower()} (so với kỳ liền trước)**")

    q_daily2 = """
        SELECT d.full_date, fod.daily_revenue
        FROM fact_order_daily fod
        JOIN dim_date d ON fod.date_key = d.date_key
        ORDER BY d.full_date
    """
    df_all = run_query(q_daily2)
    if not df_all.empty:
        dfp_all = add_period_column(df_all, "full_date", granularity)
        agg_all = (
            dfp_all.groupby(["period", "period_label"], as_index=False)["daily_revenue"].sum()
            .rename(columns={"daily_revenue": "revenue"})
            .sort_values("period")
        )
        agg_all["growth"] = agg_all["revenue"].pct_change() * 100
        agg_recent = agg_all[
            (agg_all["period"] >= pd.Timestamp(start_date) - pd.Timedelta(days=400))
            & (agg_all["period"] <= pd.Timestamp(end_date))
        ]
        fig_growth = px.bar(
            agg_recent, x="period_label", y="growth",
            title=f"% Tăng trưởng doanh thu theo {granularity.lower()} (so với kỳ liền trước)",
            color="growth", color_continuous_scale=["#ef4444", "#e5e7eb", "#10b981"], color_continuous_midpoint=0,
        )
        st.plotly_chart(fig_growth, use_container_width=True)
        with st.expander("📋 Xem bảng tăng trưởng"):
            st.dataframe(
                agg_recent.drop(columns=["period"]).rename(
                    columns={"period_label": "Kỳ", "revenue": "Doanh thu", "growth": "% Tăng trưởng"}
                ),
                use_container_width=True, hide_index=True,
            )

# ==============================================================================
# Gợi ý SQL
# ==============================================================================
with st.expander("🧠 Gợi ý SQL"):
    st.markdown("**Doanh thu theo ngày (đã pre-aggregate ở fact_order_daily):**")
    st.code(
        """SELECT d.full_date, fod.daily_revenue, fod.daily_order_count
FROM fact_order_daily fod
JOIN dim_date d ON fod.date_key = d.date_key
WHERE d.full_date BETWEEN :start_date AND :end_date
ORDER BY d.full_date;""",
        language="sql",
    )
    st.markdown("**So sánh kênh bán (Online vs Offline):**")
    st.code(
        """SELECT fo.sales_channel, SUM(fo.line_total) AS revenue,
       COUNT(DISTINCT fo.order_id) AS order_count
FROM fact_order fo
JOIN dim_date d ON fo.date_key = d.date_key
WHERE d.full_date BETWEEN :start_date AND :end_date
GROUP BY fo.sales_channel;""",
        language="sql",
    )
    st.markdown(
        "**Lưu ý quan trọng:** `sub_total`, `tax_amt`, `freight_amt`, `total_due` trong "
        "`fact_order` là field **cấp đơn hàng (header)** nhưng bị lặp lại trên từng dòng "
        "line-item. Phải `DISTINCT` theo `order_id` trước khi `SUM`, nếu không sẽ bị đếm trùng:"
    )
    st.code(
        """WITH order_header AS (
    SELECT DISTINCT order_id, date_key, sub_total, tax_amt, freight_amt, total_due
    FROM fact_order
)
SELECT SUM(tax_amt), SUM(freight_amt), SUM(total_due) FROM order_header;""",
        language="sql",
    )
