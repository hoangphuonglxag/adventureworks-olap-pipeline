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
from scipy import stats

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

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📈 Xu hướng doanh thu & AOV", "🛒 Kênh bán hàng", "💸 Chiết khấu • Thuế • Phí",
     "📊 Tăng trưởng", "🔬 Kiểm định giả thuyết"]
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
# TAB 5 — Kiểm định giả thuyết thống kê cho các nhận định phân tích
# ==============================================================================
with tab5:
    ALPHA = 0.05
    st.markdown("### 🔬 Kiểm định thống kê cho các nhận định trong bài phân tích")
    st.caption(
        "Mức ý nghĩa **α = 0.05**: nếu p-value < 0.05, ta có bằng chứng thống kê để bác bỏ giả "
        "thuyết H0 và ủng hộ nhận định tương ứng. Đây là các kiểm định đơn giản, chỉ nhằm kiểm "
        "tra xem dữ liệu có *thực sự* ủng hộ các nhận định đã nêu hay không, không thay thế cho "
        "phân tích nhân quả đầy đủ."
    )

    # ------------------------------------------------------------------
    # 1) Doanh thu có xu hướng tăng trưởng ổn định theo thời gian?
    # ------------------------------------------------------------------
    st.markdown("#### 1️⃣ Doanh thu có tăng trưởng theo thời gian không?")
    q_trend = """
        SELECT d.full_date, fod.daily_revenue
        FROM fact_order_daily fod
        JOIN dim_date d ON fod.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
        ORDER BY d.full_date
    """
    df_trend = run_query(q_trend, params)

    if df_trend.empty:
        st.info("Không có dữ liệu để kiểm định.")
    else:
        dfp_t = add_period_column(df_trend, "full_date", "Tháng")
        agg_t = (
            dfp_t.groupby(["period", "period_label"], as_index=False)["daily_revenue"]
            .sum()
            .sort_values("period")
        )
        x = range(len(agg_t))
        y = agg_t["daily_revenue"].values
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        c1, c2, c3 = st.columns(3)
        c1.metric("Hệ số góc (VNĐ/tháng)", fmt_num(slope))
        c2.metric("R²", f"{r_value ** 2:.3f}")
        c3.metric("p-value", f"{p_value:.4f}")

        if p_value < ALPHA and slope > 0:
            st.success(
                f"✅ **Ủng hộ nhận định**: doanh thu tăng trung bình khoảng {fmt_num(slope)} "
                f"VNĐ/tháng, có ý nghĩa thống kê (p = {p_value:.4f} < 0.05)."
            )
        else:
            st.warning(f"⚠️ Chưa đủ bằng chứng thống kê cho xu hướng tăng (p = {p_value:.4f}).")
        st.caption(
            "*Phương pháp: hồi quy tuyến tính doanh thu theo tháng — H0: hệ số góc = 0 "
            "(không có xu hướng), H1: hệ số góc ≠ 0.*"
        )

    st.divider()

    # ------------------------------------------------------------------
    # 2) Doanh thu Quý 2-3 (mùa hè) có cao hơn Quý 4-1 (mùa đông)?
    # ------------------------------------------------------------------
    st.markdown("#### 2️⃣ Doanh thu mùa cao điểm (Quý 2-3) có thực sự cao hơn mùa thấp điểm (Quý 4-1)?")
    if df_trend.empty:
        st.info("Không có dữ liệu để kiểm định.")
    else:
        df_q = df_trend.copy()
        df_q["full_date"] = pd.to_datetime(df_q["full_date"])
        df_q["quarter"] = df_q["full_date"].dt.quarter
        high_season = df_q.loc[df_q["quarter"].isin([2, 3]), "daily_revenue"]
        low_season = df_q.loc[df_q["quarter"].isin([1, 4]), "daily_revenue"]

        if len(high_season) > 1 and len(low_season) > 1:
            stat_u, p_u = stats.mannwhitneyu(high_season, low_season, alternative="greater")

            c1, c2, c3 = st.columns(3)
            c1.metric("TB doanh thu/ngày — Q2, Q3", fmt_num(high_season.mean()))
            c2.metric("TB doanh thu/ngày — Q1, Q4", fmt_num(low_season.mean()))
            c3.metric("p-value", f"{p_u:.4f}")

            if p_u < ALPHA:
                st.success(
                    f"✅ **Ủng hộ nhận định**: doanh thu/ngày mùa cao điểm cao hơn mùa thấp điểm "
                    f"một cách có ý nghĩa thống kê (p = {p_u:.4f} < 0.05)."
                )
            else:
                st.warning(f"⚠️ Chưa đủ bằng chứng cho sự khác biệt theo mùa (p = {p_u:.4f}).")
            st.caption(
                "*Phương pháp: kiểm định Mann-Whitney U (phi tham số, phù hợp vì doanh thu ngày "
                "thường không phân phối chuẩn) — H0: 2 nhóm có phân phối doanh thu như nhau, "
                "H1: nhóm Q2-Q3 có xu hướng cao hơn.*"
            )
        else:
            st.info("Không đủ dữ liệu ở cả hai nhóm quý để kiểm định.")

    st.divider()

    # ------------------------------------------------------------------
    # 3) AOV giữa các kênh bán hàng có khác biệt có ý nghĩa không?
    # ------------------------------------------------------------------
    st.markdown("#### 3️⃣ AOV giữa các kênh bán hàng có khác biệt có ý nghĩa thống kê không?")
    q_channel_test = """
        SELECT d.full_date, fo.sales_channel,
               SUM(fo.line_total)          AS revenue,
               COUNT(DISTINCT fo.order_id) AS order_count
        FROM fact_order fo
        JOIN dim_date d ON fo.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
          AND fo.sales_channel IS NOT NULL
        GROUP BY d.full_date, fo.sales_channel
        ORDER BY d.full_date
    """
    df_ch_test = run_query(q_channel_test, params)

    if df_ch_test.empty or df_ch_test["sales_channel"].nunique() < 2:
        st.info("Không đủ dữ liệu kênh bán để kiểm định.")
    else:
        df_ch_test["daily_aov"] = df_ch_test["revenue"] / df_ch_test["order_count"].replace(0, pd.NA)
        channel_avg = df_ch_test.groupby("sales_channel")["daily_aov"].mean().sort_values(ascending=False)
        top_channel, other_channel = channel_avg.index[0], channel_avg.index[1]

        s_top = df_ch_test.loc[df_ch_test["sales_channel"] == top_channel, "daily_aov"].dropna()
        s_other = df_ch_test.loc[df_ch_test["sales_channel"] == other_channel, "daily_aov"].dropna()

        stat_u2, p_u2 = stats.mannwhitneyu(s_top, s_other, alternative="greater")

        c1, c2, c3 = st.columns(3)
        c1.metric(f"AOV TB — {top_channel}", fmt_num(s_top.mean()))
        c2.metric(f"AOV TB — {other_channel}", fmt_num(s_other.mean()))
        c3.metric("p-value", f"{p_u2:.4f}")

        if p_u2 < ALPHA:
            st.success(
                f"✅ **Ủng hộ nhận định**: AOV kênh **{top_channel}** cao hơn kênh "
                f"**{other_channel}** một cách có ý nghĩa thống kê (p = {p_u2:.4f} < 0.05) — "
                f"phù hợp với nhận định kênh này là động lực chính về giá trị đơn hàng."
            )
        else:
            st.warning(f"⚠️ Chưa đủ bằng chứng cho sự khác biệt AOV giữa 2 kênh (p = {p_u2:.4f}).")
        st.caption(
            "*Phương pháp: kiểm định Mann-Whitney U trên AOV theo ngày của từng kênh — "
            "H0: AOV 2 kênh như nhau, H1: kênh có AOV trung bình mẫu cao hơn thực sự lớn hơn.*"
        )

    st.divider()

    # ------------------------------------------------------------------
    # 4) Doanh thu tăng có đi kèm chiết khấu & phí vận chuyển tăng không?
    # ------------------------------------------------------------------
    st.markdown("#### 4️⃣ Doanh thu tăng có thực sự đi kèm chiết khấu & phí vận chuyển tăng?")
    q_disc_test = """
        SELECT d.full_date,
               SUM(fo.order_qty * fo.unit_price * fo.unit_price_discount) AS discount_amount
        FROM fact_order fo
        JOIN dim_date d ON fo.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
        GROUP BY d.full_date
    """
    q_head_test = """
        WITH order_header AS (
            SELECT DISTINCT fo.order_id, fo.date_key, fo.freight_amt
            FROM fact_order fo
        )
        SELECT d.full_date, SUM(oh.freight_amt) AS freight_amt
        FROM order_header oh
        JOIN dim_date d ON oh.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
        GROUP BY d.full_date
    """
    df_disc_t = run_query(q_disc_test, params)
    df_head_t = run_query(q_head_test, params)

    if df_disc_t.empty or df_head_t.empty or df_trend.empty:
        st.info("Không đủ dữ liệu để kiểm định tương quan.")
    else:
        df_corr = (
            df_trend.merge(df_disc_t, on="full_date", how="inner")
            .merge(df_head_t, on="full_date", how="inner")
        )
        dfp_c = add_period_column(df_corr, "full_date", "Tháng")
        agg_c = dfp_c.groupby("period", as_index=False).agg(
            revenue=("daily_revenue", "sum"),
            discount_amount=("discount_amount", "sum"),
            freight_amt=("freight_amt", "sum"),
        )

        r_disc, p_disc = stats.pearsonr(agg_c["revenue"], agg_c["discount_amount"])
        r_frt, p_frt = stats.pearsonr(agg_c["revenue"], agg_c["freight_amt"])

        c1, c2 = st.columns(2)
        c1.metric("Tương quan Doanh thu ↔ Chiết khấu (r)", f"{r_disc:.3f}", f"p = {p_disc:.4f}")
        c2.metric("Tương quan Doanh thu ↔ Phí vận chuyển (r)", f"{r_frt:.3f}", f"p = {p_frt:.4f}")

        supported = []
        if p_disc < ALPHA and r_disc > 0:
            supported.append(f"chiết khấu (r = {r_disc:.2f})")
        if p_frt < ALPHA and r_frt > 0:
            supported.append(f"phí vận chuyển (r = {r_frt:.2f})")

        if supported:
            st.success(
                f"✅ **Ủng hộ nhận định**: doanh thu theo tháng tương quan dương có ý nghĩa thống kê "
                f"với {' và '.join(supported)} — phù hợp với nhận định về chiến lược tăng trưởng "
                f"đánh đổi biên lợi nhuận (volume-driven)."
            )
        else:
            st.warning("⚠️ Chưa tìm thấy tương quan dương có ý nghĩa giữa doanh thu và chiết khấu/phí vận chuyển.")
        st.caption(
            "*Phương pháp: hệ số tương quan Pearson theo tháng — H0: r = 0 (không tương quan), "
            "H1: r > 0 (tương quan dương).*"
        )

    st.divider()

    # ------------------------------------------------------------------
    # 5) Chiết khấu có thực sự đồng đều bất kể quy mô đơn hàng?
    # ------------------------------------------------------------------
    st.markdown("#### 5️⃣ Tỷ lệ chiết khấu có đồng đều giữa đơn hàng lớn/nhỏ không?")
    q_order_disc = """
        WITH order_level AS (
            SELECT DISTINCT fo.order_id, fo.date_key, fo.sub_total
            FROM fact_order fo
        ),
        order_discount AS (
            SELECT fo.order_id, AVG(fo.unit_price_discount) AS avg_discount_rate
            FROM fact_order fo
            GROUP BY fo.order_id
        )
        SELECT ol.sub_total, od.avg_discount_rate
        FROM order_level ol
        JOIN order_discount od ON ol.order_id = od.order_id
        JOIN dim_date d ON ol.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
    """
    df_od = run_query(q_order_disc, params)

    if df_od.empty or len(df_od) < 3:
        st.info("Không đủ dữ liệu ở cấp đơn hàng để kiểm định.")
    else:
        r_od, p_od = stats.pearsonr(df_od["sub_total"], df_od["avg_discount_rate"])

        c1, c2 = st.columns(2)
        c1.metric("Tương quan Quy mô đơn hàng ↔ % Chiết khấu (r)", f"{r_od:.3f}")
        c2.metric("p-value", f"{p_od:.4f}")

        if p_od >= ALPHA or abs(r_od) < 0.2:
            st.success(
                f"✅ **Ủng hộ nhận định**: tương quan giữa quy mô đơn hàng và tỷ lệ chiết khấu rất "
                f"yếu (r = {r_od:.2f}, p = {p_od:.4f}) — cho thấy chiết khấu **chưa** thực sự được "
                f"phân cấp theo quy mô đơn hàng, đúng như nhận định và là cơ sở cho đề xuất chính "
                f"sách chiết khấu theo bậc."
            )
        else:
            st.warning(
                f"⚠️ Có tương quan giữa quy mô đơn hàng và tỷ lệ chiết khấu (r = {r_od:.2f}, "
                f"p = {p_od:.4f}) — chiết khấu hiện tại có thể đã được phân cấp phần nào theo quy mô."
            )
        st.caption(
            "*Phương pháp: hệ số tương quan Pearson giữa `sub_total` (quy mô đơn hàng) và tỷ lệ "
            "chiết khấu trung bình mỗi đơn — r gần 0 nghĩa là mức chiết khấu không phụ thuộc nhiều "
            "vào quy mô đơn hàng.*"
        )

    st.divider()
    st.markdown("### 💡 Kiểm định riêng cho 3 đề xuất cải thiện")

    # ------------------------------------------------------------------
    # 6) ĐỀ XUẤT 1 — Chiết khấu theo nhiều cấp dựa trên quy mô đơn hàng
    # ------------------------------------------------------------------
    st.markdown(
        "#### 6️⃣ Đề xuất *'chiết khấu theo nhiều cấp'*: tỷ lệ chiết khấu giữa các nhóm "
        "quy mô đơn hàng có thực sự đồng đều không?"
    )
    if df_od.empty or len(df_od) < 8:
        st.info("Không đủ dữ liệu cấp đơn hàng để kiểm định.")
    else:
        df_bucket = df_od.copy()
        try:
            df_bucket["size_bucket"] = pd.qcut(
                df_bucket["sub_total"], 4, labels=["Q1 (nhỏ nhất)", "Q2", "Q3", "Q4 (lớn nhất)"]
            )
        except ValueError:
            df_bucket["size_bucket"] = pd.cut(df_bucket["sub_total"], 4)

        bucket_groups = [
            g["avg_discount_rate"].values for _, g in df_bucket.groupby("size_bucket", observed=True)
            if len(g) > 0
        ]

        if len(bucket_groups) >= 2:
            stat_kw, p_kw = stats.kruskal(*bucket_groups)

            bucket_summary = (
                df_bucket.groupby("size_bucket", observed=True)
                .agg(so_don=("sub_total", "count"), gia_tri_tb=("sub_total", "mean"),
                     chiet_khau_tb=("avg_discount_rate", "mean"))
                .reset_index()
            )

            fig_bucket = px.bar(
                bucket_summary, x="size_bucket", y="chiet_khau_tb",
                title="Tỷ lệ chiết khấu trung bình theo nhóm quy mô đơn hàng (tứ phân vị)",
                color_discrete_sequence=["#a855f7"],
            )
            fig_bucket.update_yaxes(title="% Chiết khấu TB", tickformat=".1%")
            st.plotly_chart(fig_bucket, use_container_width=True)

            st.dataframe(
                bucket_summary.rename(columns={
                    "size_bucket": "Nhóm quy mô", "so_don": "Số đơn",
                    "gia_tri_tb": "Giá trị đơn TB", "chiet_khau_tb": "% Chiết khấu TB",
                }).style.format({"Giá trị đơn TB": "{:,.0f}", "% Chiết khấu TB": "{:.1%}"}),
                use_container_width=True, hide_index=True,
            )
            st.metric("p-value (Kruskal-Wallis, 4 nhóm)", f"{p_kw:.4f}")

            if p_kw >= ALPHA:
                st.success(
                    f"✅ **Ủng hộ đề xuất**: không có khác biệt có ý nghĩa thống kê về tỷ lệ chiết "
                    f"khấu giữa 4 nhóm quy mô đơn hàng (p = {p_kw:.4f} ≥ 0.05) — đơn hàng lớn và đơn "
                    f"hàng nhỏ hiện đang nhận mức chiết khấu gần như nhau. Đây là cơ sở hợp lý để xây "
                    f"dựng chính sách chiết khấu theo nhiều cấp thay vì áp dụng đồng đều."
                )
            else:
                st.warning(
                    f"⚠️ Có khác biệt về tỷ lệ chiết khấu giữa các nhóm quy mô (p = {p_kw:.4f} < 0.05) "
                    "— chính sách hiện tại có thể đã phân hóa phần nào; nên xem biểu đồ trên để đánh "
                    "giá chiều hướng trước khi thiết kế lại các bậc chiết khấu."
                )
            st.caption(
                "*Phương pháp: kiểm định Kruskal-Wallis (mở rộng Mann-Whitney cho >2 nhóm) trên 4 nhóm "
                "tứ phân vị theo `sub_total` — H0: tỷ lệ chiết khấu TB của 4 nhóm bằng nhau, H1: có ít "
                "nhất 1 nhóm khác biệt.*"
            )
            st.caption(
                "*Phương pháp: kiểm định Kruskal-Wallis (mở rộng Mann-Whitney cho >2 nhóm) trên 4 nhóm "
                "tứ phân vị theo `sub_total` — H0: tỷ lệ chiết khấu TB của 4 nhóm bằng nhau, H1: có ít "
                "nhất 1 nhóm khác biệt.*"
            )
        else:
            st.info("Không đủ nhóm để so sánh.")

    st.markdown("**6b · Chiết khấu có thực sự ăn vào biên lợi nhuận gộp không? (dùng giá vốn thật từ `dim_product`)**")
    q_margin = """
        WITH order_lines AS (
            SELECT fo.order_id, fo.line_total, fo.order_qty, fo.unit_price_discount,
                   dp.standard_cost
            FROM fact_order fo
            JOIN dim_product dp ON fo.product_key = dp.product_key
            JOIN dim_date d ON fo.date_key = d.date_key
            WHERE d.full_date BETWEEN :start_date AND :end_date
        )
        SELECT order_id,
               SUM(line_total)               AS revenue,
               SUM(order_qty * standard_cost) AS total_cost,
               AVG(unit_price_discount)       AS avg_discount_rate
        FROM order_lines
        GROUP BY order_id
    """
    df_margin = run_query(q_margin, params)

    if df_margin.empty or len(df_margin) < 8:
        st.info("Không đủ dữ liệu để tính biên lợi nhuận theo đơn hàng.")
    else:
        df_margin = df_margin[df_margin["revenue"] > 0].copy()
        df_margin["gross_profit"] = df_margin["revenue"] - df_margin["total_cost"]
        df_margin["margin_pct"] = df_margin["gross_profit"] / df_margin["revenue"]
        df_margin = df_margin.replace([float("inf"), float("-inf")], pd.NA).dropna(
            subset=["margin_pct", "avg_discount_rate"]
        )

        if len(df_margin) < 8:
            st.info("Không đủ dữ liệu hợp lệ để kiểm định.")
        else:
            slope_m, intercept_m, r_m, p_m, se_m = stats.linregress(
                df_margin["avg_discount_rate"], df_margin["margin_pct"]
            )

            try:
                df_margin["size_bucket2"] = pd.qcut(
                    df_margin["revenue"], 4, labels=["Q1 (nhỏ nhất)", "Q2", "Q3", "Q4 (lớn nhất)"]
                )
            except ValueError:
                df_margin["size_bucket2"] = pd.cut(df_margin["revenue"], 4)

            margin_bucket = (
                df_margin.groupby("size_bucket2", observed=True)
                .agg(so_don=("revenue", "count"), doanh_thu_tb=("revenue", "mean"),
                     chiet_khau_tb=("avg_discount_rate", "mean"), bien_loi_nhuan_tb=("margin_pct", "mean"))
                .reset_index()
            )

            c1, c2 = st.columns(2)
            # slope_m: Δ(margin_pct) / Δ(discount_rate), cả hai đều ở dạng phân số (0-1)
            # → mỗi +1 điểm % chiết khấu (0.01) làm margin đổi slope_m * 0.01, quy về điểm % nhân 100
            margin_change_per_1pct_discount = slope_m * 0.01 * 100
            c1.metric("Tương quan Chiết khấu ↔ Biên lợi nhuận (r)", f"{r_m:.3f}", f"p = {p_m:.4f}")
            c2.metric("Mỗi +1 điểm % chiết khấu → biên LN đổi", f"{margin_change_per_1pct_discount:.2f} điểm %")

            fig_margin = px.bar(
                margin_bucket, x="size_bucket2", y="bien_loi_nhuan_tb",
                title="Biên lợi nhuận gộp trung bình theo nhóm quy mô đơn hàng",
                color_discrete_sequence=["#ef4444"],
            )
            fig_margin.update_yaxes(title="Biên lợi nhuận gộp TB", tickformat=".1%")
            st.plotly_chart(fig_margin, use_container_width=True)

            st.dataframe(
                margin_bucket.rename(columns={
                    "size_bucket2": "Nhóm quy mô", "so_don": "Số đơn", "doanh_thu_tb": "Doanh thu TB/đơn",
                    "chiet_khau_tb": "% Chiết khấu TB", "bien_loi_nhuan_tb": "% Biên lợi nhuận gộp TB",
                }).style.format({
                    "Doanh thu TB/đơn": "{:,.0f}", "% Chiết khấu TB": "{:.1%}", "% Biên lợi nhuận gộp TB": "{:.1%}",
                }),
                use_container_width=True, hide_index=True,
            )

            if p_m < ALPHA and r_m < 0:
                st.success(
                    f"✅ **Ủng hộ đề xuất**: chiết khấu tương quan âm có ý nghĩa thống kê với biên lợi "
                    f"nhuận gộp thực tế (r = {r_m:.2f}, p = {p_m:.4f}) — chiết khấu càng cao, biên lợi "
                    f"nhuận càng bị bào mòn. Kết hợp với kiểm định 6a (chiết khấu chưa phân hóa theo quy "
                    f"mô), đây là bằng chứng trực tiếp cho thấy chính sách chiết khấu theo nhiều cấp sẽ "
                    f"giúp bảo vệ biên lợi nhuận tốt hơn cách làm hiện tại."
                )
            else:
                st.warning(
                    f"⚠️ Chưa thấy tương quan âm rõ ràng giữa chiết khấu và biên lợi nhuận gộp "
                    f"(r = {r_m:.2f}, p = {p_m:.4f})."
                )
            st.caption(
                "*Phương pháp: hồi quy tuyến tính biên lợi nhuận gộp (= (doanh thu − giá vốn) / doanh "
                "thu, dùng `standard_cost` từ `dim_product`) theo tỷ lệ chiết khấu ở cấp đơn hàng — "
                "H0: hệ số góc = 0, H1: hệ số góc < 0 (chiết khấu tăng → biên lợi nhuận giảm). Đây là "
                "**biên lợi nhuận gộp**, chưa trừ chi phí vận hành khác nên không hoàn toàn tương đương "
                "'biên lợi nhuận ròng' được nhắc trong đề xuất.*"
            )

    st.divider()

    # ------------------------------------------------------------------
    # 7) ĐỀ XUẤT 2 — Quỹ dự phòng tài chính từ doanh thu mùa cao điểm
    # ------------------------------------------------------------------
    st.markdown(
        "#### 7️⃣ Đề xuất *'quỹ dự phòng từ Quý 2-3'*: tính mùa vụ có đủ mạnh & lặp lại ổn định "
        "qua các năm để làm căn cứ không?"
    )
    if df_trend.empty:
        st.info("Không có dữ liệu để kiểm định.")
    else:
        df_season = df_trend.copy()
        df_season["full_date"] = pd.to_datetime(df_season["full_date"])
        df_season["year"] = df_season["full_date"].dt.year
        df_season["quarter"] = df_season["full_date"].dt.quarter

        quarter_groups = [g["daily_revenue"].values for _, g in df_season.groupby("quarter")]
        if len(quarter_groups) == 4:
            stat_kw2, p_kw2 = stats.kruskal(*quarter_groups)
            st.metric("p-value (Kruskal-Wallis, 4 quý)", f"{p_kw2:.4f}")
            if p_kw2 < ALPHA:
                st.success(
                    f"✅ Doanh thu khác biệt rất có ý nghĩa thống kê giữa 4 quý (p = {p_kw2:.4f} < 0.05) "
                    "— tính mùa vụ là có thật trên toàn bộ dữ liệu, không chỉ khi gộp nhóm Q2-3 vs Q1-4."
                )
            else:
                st.warning(f"⚠️ Chưa đủ bằng chứng cho khác biệt giữa 4 quý (p = {p_kw2:.4f}).")

        year_q = df_season.groupby(["year", "quarter"])["daily_revenue"].sum().unstack(fill_value=0)
        year_q = year_q.reindex(columns=[1, 2, 3, 4], fill_value=0)
        year_q_share = year_q.div(year_q.sum(axis=1).replace(0, pd.NA), axis=0) * 100
        year_q_share["Q2+Q3 (%)"] = year_q_share[2] + year_q_share[3]

        st.markdown("**Tỷ trọng doanh thu Quý 2+3 theo từng năm** (căn cứ ước lượng quy mô quỹ dự phòng):")
        st.dataframe(
            year_q_share[["Q2+Q3 (%)"]].reset_index().rename(columns={"year": "Năm"})
            .style.format({"Q2+Q3 (%)": "{:.1f}%"}),
            use_container_width=True, hide_index=True,
        )

        n_years = year_q_share["Q2+Q3 (%)"].notna().sum()
        n_years_over_half = (year_q_share["Q2+Q3 (%)"] > 50).sum()
        avg_share = year_q_share["Q2+Q3 (%)"].mean()
        std_share = year_q_share["Q2+Q3 (%)"].std()

        if n_years >= 2 and n_years_over_half == n_years:
            st.success(
                f"✅ **Ủng hộ đề xuất**: cả {n_years}/{n_years} năm trong dữ liệu, Quý 2+3 đều chiếm "
                f"trên 50% doanh thu cả năm (TB {avg_share:.1f}%, độ lệch chuẩn {std_share:.1f} điểm %). "
                f"Mô hình mùa vụ lặp lại ổn định qua các năm — đủ cơ sở để trích lập quỹ dự phòng tài "
                f"chính từ giai đoạn cao điểm này."
            )
        else:
            st.warning(
                f"⚠️ Chỉ {n_years_over_half}/{n_years} năm có Quý 2+3 chiếm trên 50% doanh thu — "
                "mô hình mùa vụ chưa hoàn toàn nhất quán qua các năm, nên xem thêm bảng chi tiết ở trên."
            )
        st.caption(
            "*Phương pháp: (1) Kruskal-Wallis kiểm định khác biệt doanh thu giữa 4 quý; (2) kiểm tra "
            "tính nhất quán của tỷ trọng doanh thu Quý 2+3 qua từng năm — càng nhất quán, quỹ dự phòng "
            "dựa trên quy luật này càng đáng tin cậy.*"
        )

    st.divider()

    # ------------------------------------------------------------------
    # 8) ĐỀ XUẤT 3 — Đa dạng hóa danh mục sản phẩm mùa đông / ít mùa vụ
    # ------------------------------------------------------------------
    st.markdown(
        "#### 8️⃣ Đề xuất *'mở rộng danh mục sản phẩm ít chịu ảnh hưởng mùa vụ'*: danh mục nào "
        "đang ổn định quanh năm, danh mục nào đang gây ra sự phụ thuộc mùa vụ?"
    )
    q_cat = """
        SELECT d.full_date, dp.category_name, SUM(fo.line_total) AS revenue
        FROM fact_order fo
        JOIN dim_date d ON fo.date_key = d.date_key
        JOIN dim_product dp ON fo.product_key = dp.product_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
          AND dp.category_name IS NOT NULL
        GROUP BY d.full_date, dp.category_name
        ORDER BY d.full_date
    """
    df_cat = run_query(q_cat, params)

    if df_cat.empty:
        st.info("Không có dữ liệu danh mục sản phẩm trong khoảng thời gian đã chọn.")
    else:
        df_cat["full_date"] = pd.to_datetime(df_cat["full_date"])
        df_cat["quarter"] = df_cat["full_date"].dt.quarter

        cat_quarter_total = (
            df_cat.groupby(["category_name", "quarter"])["revenue"].sum().unstack(fill_value=0)
        )
        cat_quarter_total = cat_quarter_total.reindex(columns=[1, 2, 3, 4], fill_value=0)
        cat_total = cat_quarter_total.sum(axis=1)
        cat_mean = cat_quarter_total.mean(axis=1).replace(0, pd.NA)
        cat_cv = (cat_quarter_total.std(axis=1) / cat_mean * 100)
        cat_peak = cat_quarter_total.idxmax(axis=1)

        # Kruskal-Wallis riêng cho từng danh mục (trên doanh thu ngày, nhóm theo quý)
        kw_p = {}
        for cat, g in df_cat.groupby("category_name"):
            groups = [gg["revenue"].values for _, gg in g.groupby("quarter") if len(gg) >= 5]
            if len(groups) == 4:
                try:
                    _, p_val = stats.kruskal(*groups)
                    kw_p[cat] = p_val
                except ValueError:
                    kw_p[cat] = None
            else:
                kw_p[cat] = None

        summary_cat = pd.DataFrame({
            "Tổng doanh thu": cat_total,
            "CV mùa vụ (%)": cat_cv,
            "Quý cao điểm": "Q" + cat_peak.astype(str),
        })
        summary_cat["p-value (4 quý)"] = summary_cat.index.map(kw_p)
        summary_cat["Mùa vụ rõ rệt?"] = summary_cat["p-value (4 quý)"].apply(
            lambda p: "Có" if (p is not None and p < ALPHA) else ("Không đủ dữ liệu" if p is None else "Không rõ")
        )
        summary_cat = summary_cat.sort_values("Tổng doanh thu", ascending=False).reset_index()
        summary_cat = summary_cat.rename(columns={"category_name": "Danh mục"})

        top_n = min(8, len(summary_cat))
        top_categories = summary_cat.head(top_n)["Danh mục"].tolist()

        cat_share = cat_quarter_total.div(cat_total.replace(0, pd.NA), axis=0) * 100
        cat_share_long = cat_share.reset_index().melt(
            id_vars="category_name", var_name="quarter", value_name="share"
        )
        cat_share_long["quarter"] = "Q" + cat_share_long["quarter"].astype(str)
        cat_share_long = cat_share_long[cat_share_long["category_name"].isin(top_categories)]

        fig_cat = px.bar(
            cat_share_long, x="category_name", y="share", color="quarter", barmode="group",
            title=f"Tỷ trọng doanh thu theo quý — Top {top_n} danh mục theo doanh thu",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_cat.update_yaxes(title="% doanh thu trong danh mục")
        fig_cat.update_xaxes(title="Danh mục")
        st.plotly_chart(fig_cat, use_container_width=True)

        st.dataframe(
            summary_cat.style.format({"Tổng doanh thu": "{:,.0f}", "CV mùa vụ (%)": "{:.1f}",
                                       "p-value (4 quý)": lambda v: f"{v:.4f}" if pd.notna(v) else "—"}),
            use_container_width=True, hide_index=True,
        )

        candidates = summary_cat[summary_cat["Mùa vụ rõ rệt?"] == "Không rõ"].sort_values("CV mùa vụ (%)")
        seasonal_cats = summary_cat[summary_cat["Mùa vụ rõ rệt?"] == "Có"].sort_values(
            "CV mùa vụ (%)", ascending=False
        )

        if not candidates.empty:
            names = ", ".join(candidates.head(3)["Danh mục"].tolist())
            st.success(
                f"✅ **Ủng hộ đề xuất**: danh mục **{names}** có doanh thu phân bổ khá đều quanh năm "
                f"(CV thấp, chưa có bằng chứng mùa vụ rõ rệt theo Kruskal-Wallis) — đây là những ứng "
                f"viên phù hợp để ưu tiên mở rộng nhằm giảm phụ thuộc vào mùa cao điểm."
            )
        if not seasonal_cats.empty:
            names2 = ", ".join(seasonal_cats.head(3)["Danh mục"].tolist())
            st.info(
                f"ℹ️ Ngược lại, danh mục **{names2}** có tính mùa vụ rõ rệt nhất (CV cao, p < 0.05) — "
                "đây chính là nhóm sản phẩm đang tạo ra sự phụ thuộc vào Quý 2-3 mà đề xuất muốn giảm bớt."
            )
        st.caption(
            "*Phương pháp: (1) hệ số biến thiên CV = độ lệch chuẩn / trung bình doanh thu 4 quý — CV "
            "càng thấp, doanh thu danh mục càng ổn định quanh năm; (2) kiểm định Kruskal-Wallis doanh "
            "thu ngày theo quý, chạy riêng cho từng danh mục, để xác nhận mùa vụ có ý nghĩa thống kê hay "
            "không (yêu cầu tối thiểu 5 ngày dữ liệu/quý để chạy kiểm định).*"
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
