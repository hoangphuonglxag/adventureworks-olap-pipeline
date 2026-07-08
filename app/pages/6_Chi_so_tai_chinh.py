"""
6_Chi_so_Tai_chinh.py — Các chỉ số tài chính có thể tính từ Gold DW hiện có
Nguồn: fact_product_daily · fact_order_daily · fact_inventory · dim_product · dim_date

LƯU Ý PHẠM VI:
DW hiện tại chỉ có dữ liệu bán hàng (sales) và tồn kho (quantity), KHÔNG có dữ liệu
bảng cân đối kế toán (tài sản, nợ, vốn chủ sở hữu, tiền mặt, chi phí vận hành, thuế TNDN).
Do đó trang này CHỈ tính các chỉ số có thể suy ra trực tiếp từ fact bán hàng/tồn kho:
Doanh thu, Lợi nhuận gộp, Biên LN gộp, Vòng quay tồn kho / Ngày tồn kho.
Các chỉ số còn lại (Lợi nhuận ròng, Biên LN ròng, Dòng tiền, Current/Quick Ratio, ROA, ROE)
được liệt kê ở cuối trang kèm lý do và dữ liệu cần bổ sung để tính được trong tương lai.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from utils.db import run_query, get_date_bounds, clear_cache, fmt_num, fmt_pct, safe_div, db_connection_guard
from utils.helpers import normalize_date_range, add_period_column, growth_pct, GRANULARITY_OPTIONS

st.set_page_config(page_title="Chỉ số Tài chính", page_icon="💹", layout="wide")
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

    granularity = st.selectbox("Xem theo", GRANULARITY_OPTIONS, index=2)

params = {"start_date": start_date, "end_date": end_date}
days_in_range = max((end_date - start_date).days + 1, 1)

st.title("💹 Chỉ số Tài chính")
st.caption("Nguồn dữ liệu: `fact_product_daily` · `fact_order_daily` · `fact_inventory` · `dim_product`")

tab1, tab2, tab3 = st.tabs(["💰 Doanh thu & Lợi nhuận", "📦 Vòng quay tồn kho", "🚫 Chỉ số chưa thể tính"])

# ==============================================================================
# TAB 1 — Doanh thu, Lợi nhuận gộp, Biên lợi nhuận gộp
# ==============================================================================
with tab1:
    q_trend = """
        SELECT d.full_date,
               SUM(fpd.revenue)       AS revenue,
               SUM(fpd.gross_profit)  AS gross_profit
        FROM fact_product_daily fpd
        JOIN dim_date d ON fpd.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
        GROUP BY d.full_date
        ORDER BY d.full_date
    """
    df_trend = run_query(q_trend, params)

    if df_trend.empty:
        st.info("Không có dữ liệu trong khoảng thời gian đã chọn.")
    else:
        total_revenue = df_trend["revenue"].sum()
        total_gross_profit = df_trend["gross_profit"].sum()
        overall_margin = safe_div(total_gross_profit, total_revenue)

        # So sánh với kỳ liền trước có cùng độ dài
        prev_end = start_date - pd.Timedelta(days=1)
        prev_start = prev_end - pd.Timedelta(days=days_in_range - 1)
        q_prev = """
            SELECT COALESCE(SUM(fpd.revenue), 0) AS revenue, COALESCE(SUM(fpd.gross_profit), 0) AS gross_profit
            FROM fact_product_daily fpd
            JOIN dim_date d ON fpd.date_key = d.date_key
            WHERE d.full_date BETWEEN :prev_start AND :prev_end
        """
        df_prev = run_query(q_prev, {"prev_start": prev_start, "prev_end": prev_end})
        prev_revenue = df_prev["revenue"].iloc[0] if not df_prev.empty else None
        prev_gross_profit = df_prev["gross_profit"].iloc[0] if not df_prev.empty else None
        prev_margin = safe_div(prev_gross_profit, prev_revenue) if prev_revenue else None

        rev_growth = growth_pct(total_revenue, prev_revenue)
        gp_growth = growth_pct(total_gross_profit, prev_gross_profit)
        margin_growth = growth_pct(overall_margin, prev_margin) if overall_margin is not None and prev_margin is not None else None

        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Doanh thu (Revenue)", fmt_num(total_revenue), fmt_pct(rev_growth) + " so với kỳ trước" if rev_growth is not None else None)
        c2.metric("📐 Lợi nhuận gộp (Gross Profit)", fmt_num(total_gross_profit), fmt_pct(gp_growth) + " so với kỳ trước" if gp_growth is not None else None)
        c3.metric(
            "📊 Biên LN gộp (Gross Margin)",
            fmt_pct(overall_margin * 100 if overall_margin is not None else None),
            fmt_pct(margin_growth) + " so với kỳ trước" if margin_growth is not None else None,
        )
        st.caption(
            f"So sánh với kỳ liền trước cùng độ dài ({prev_start} → {prev_end}, {days_in_range} ngày)."
        )

        st.divider()
        df_period = add_period_column(df_trend, "full_date", granularity)
        agg_period = (
            df_period.groupby(["period", "period_label"], as_index=False)
            .agg(revenue=("revenue", "sum"), gross_profit=("gross_profit", "sum"))
            .sort_values("period")
        )
        agg_period["gross_margin_pct"] = agg_period["gross_profit"] / agg_period["revenue"].replace(0, pd.NA) * 100

        fig_trend = make_subplots(specs=[[{"secondary_y": True}]])
        fig_trend.add_trace(
            go.Bar(x=agg_period["period_label"], y=agg_period["revenue"], name="Doanh thu", marker_color="#6366f1"),
            secondary_y=False,
        )
        fig_trend.add_trace(
            go.Bar(x=agg_period["period_label"], y=agg_period["gross_profit"], name="Lợi nhuận gộp", marker_color="#10b981"),
            secondary_y=False,
        )
        fig_trend.add_trace(
            go.Scatter(x=agg_period["period_label"], y=agg_period["gross_margin_pct"], name="Biên LN gộp (%)",
                       line=dict(color="#f59e0b", width=3)),
            secondary_y=True,
        )
        fig_trend.update_layout(title=f"Doanh thu & Lợi nhuận gộp theo {granularity.lower()}", height=450, barmode="group")
        fig_trend.update_yaxes(title_text="Giá trị", secondary_y=False)
        fig_trend.update_yaxes(title_text="Biên LN gộp (%)", secondary_y=True)
        st.plotly_chart(fig_trend, use_container_width=True)

        show_trend = agg_period[["period_label", "revenue", "gross_profit", "gross_margin_pct"]].copy()
        show_trend.columns = ["Kỳ", "Doanh thu", "Lợi nhuận gộp", "Biên LN gộp (%)"]
        st.dataframe(
            show_trend.style.format({"Doanh thu": "{:,.0f}", "Lợi nhuận gộp": "{:,.0f}", "Biên LN gộp (%)": "{:,.1f}%"}),
            use_container_width=True, hide_index=True,
        )

# ==============================================================================
# TAB 2 — Vòng quay tồn kho / Ngày tồn kho (Inventory Turnover / DIO)
# ==============================================================================
with tab2:
    st.markdown(
        "**Vòng quay hàng tồn kho** và **Số ngày tồn kho (DIO)** được ước lượng từ giá vốn hàng bán (COGS) "
        "trong kỳ đã chọn và giá trị tồn kho **hiện tại** (snapshot), vì `fact_inventory` không có `date_key` "
        "để tách theo thời gian."
    )

    q_cogs = """
        SELECT COALESCE(SUM(fpd.revenue), 0) AS revenue, COALESCE(SUM(fpd.gross_profit), 0) AS gross_profit
        FROM fact_product_daily fpd
        JOIN dim_date d ON fpd.date_key = d.date_key
        WHERE d.full_date BETWEEN :start_date AND :end_date
    """
    df_cogs = run_query(q_cogs, params)

    q_inv_value = """
        SELECT dp.category_name,
               SUM(fi.quantity)                      AS ton_kho_sl,
               SUM(fi.quantity * dp.standard_cost)    AS ton_kho_gia_tri
        FROM fact_inventory fi
        JOIN dim_product dp ON fi.product_key = dp.product_key
        WHERE dp.is_current = TRUE
        GROUP BY dp.category_name
    """
    df_inv_value = run_query(q_inv_value)

    if df_cogs.empty or df_inv_value.empty:
        st.info("Không đủ dữ liệu bán hàng hoặc tồn kho để tính vòng quay tồn kho.")
    else:
        total_revenue = df_cogs["revenue"].iloc[0]
        total_gross_profit = df_cogs["gross_profit"].iloc[0]
        total_cogs = total_revenue - total_gross_profit  # Giá vốn hàng bán = Doanh thu - LN gộp
        total_inv_value = df_inv_value["ton_kho_gia_tri"].sum()

        daily_cogs = total_cogs / days_in_range if days_in_range else None
        dio_days = safe_div(total_inv_value, daily_cogs) if daily_cogs else None
        turnover_annualized = safe_div(365, dio_days) if dio_days else None

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🧾 Giá vốn hàng bán (COGS) — kỳ chọn", fmt_num(total_cogs))
        c2.metric("📦 Giá trị tồn kho hiện tại", fmt_num(total_inv_value))
        c3.metric("📅 Số ngày tồn kho (DIO)", f"{dio_days:,.0f} ngày" if dio_days is not None else "—")
        c4.metric("🔄 Vòng quay tồn kho (năm hoá)", f"{turnover_annualized:,.1f} lần/năm" if turnover_annualized is not None else "—")

        st.divider()
        df_inv_value["margin_gop_pct"] = None
        cat_cogs = run_query(
            """
            SELECT dp.category_name,
                   COALESCE(SUM(fpd.revenue), 0) AS revenue,
                   COALESCE(SUM(fpd.gross_profit), 0) AS gross_profit
            FROM fact_product_daily fpd
            JOIN dim_product dp ON fpd.product_key = dp.product_key
            JOIN dim_date d ON fpd.date_key = d.date_key
            WHERE d.full_date BETWEEN :start_date AND :end_date
            GROUP BY dp.category_name
            """,
            params,
        )
        cat_merge = df_inv_value.merge(cat_cogs, on="category_name", how="left").fillna(0)
        cat_merge["cogs"] = cat_merge["revenue"] - cat_merge["gross_profit"]
        cat_merge["daily_cogs"] = cat_merge["cogs"] / days_in_range
        cat_merge["dio_days"] = cat_merge.apply(
            lambda r: (r["ton_kho_gia_tri"] / r["daily_cogs"]) if r["daily_cogs"] > 0 else None, axis=1
        )

        fig_dio = px.bar(
            cat_merge.sort_values("dio_days", ascending=True, na_position="first"),
            x="dio_days", y="category_name", orientation="h",
            title="Số ngày tồn kho (DIO) theo danh mục", color_discrete_sequence=["#6366f1"],
            labels={"dio_days": "Số ngày tồn kho", "category_name": "Danh mục"},
        )
        fig_dio.update_layout(height=400)
        st.plotly_chart(fig_dio, use_container_width=True)

        show_inv = cat_merge[["category_name", "ton_kho_gia_tri", "cogs", "dio_days"]].copy()
        show_inv.columns = ["Danh mục", "Giá trị tồn kho hiện tại", "COGS (kỳ chọn)", "Số ngày tồn kho"]
        st.dataframe(
            show_inv.style.format({"Giá trị tồn kho hiện tại": "{:,.0f}", "COGS (kỳ chọn)": "{:,.0f}", "Số ngày tồn kho": "{:,.0f}"}),
            use_container_width=True, hide_index=True,
        )

# ==============================================================================
# TAB 3 — Các chỉ số chưa thể tính từ dữ liệu hiện có
# ==============================================================================
with tab3:
    st.markdown("### Các chỉ số chưa thể tính từ Gold DW hiện tại")
    st.markdown(
        "DW hiện chỉ có fact bán hàng (`fact_order`, `fact_product_daily`, `fact_order_daily`, `fact_seller_daily`) "
        "và fact tồn kho theo số lượng (`fact_inventory`), **không có dữ liệu bảng cân đối kế toán / chi phí vận hành / "
        "thuế TNDN / dòng tiền**. Do đó các chỉ số sau chưa thể tính chính xác:"
    )

    missing_metrics = pd.DataFrame(
        [
            {
                "Chỉ số": "Lợi nhuận ròng (Net Profit)",
                "Công thức": "Doanh thu − Tất cả chi phí (SG&A, lãi vay...) − Thuế TNDN",
                "Dữ liệu còn thiếu": "Chi phí vận hành (opex), chi phí lãi vay, thuế TNDN theo kỳ",
            },
            {
                "Chỉ số": "Biên LN ròng (Net Margin)",
                "Công thức": "Lợi nhuận ròng / Doanh thu × 100%",
                "Dữ liệu còn thiếu": "Phụ thuộc Lợi nhuận ròng ở trên",
            },
            {
                "Chỉ số": "Dòng tiền (Cash Flow)",
                "Công thức": "Thu tiền mặt − Chi tiền mặt theo kỳ",
                "Dữ liệu còn thiếu": "Sổ nhật ký tiền mặt / bảng thu-chi (không có trong DW bán hàng)",
            },
            {
                "Chỉ số": "Hệ số thanh toán hiện hành (Current Ratio)",
                "Công thức": "Tài sản ngắn hạn / Nợ ngắn hạn",
                "Dữ liệu còn thiếu": "Bảng cân đối kế toán: tài sản ngắn hạn, nợ ngắn hạn",
            },
            {
                "Chỉ số": "Hệ số thanh toán nhanh (Quick Ratio)",
                "Công thức": "(Tài sản ngắn hạn − Hàng tồn kho) / Nợ ngắn hạn",
                "Dữ liệu còn thiếu": "Bảng cân đối kế toán (giá trị tồn kho $ đã có thể ước lượng, nhưng thiếu tài sản/nợ ngắn hạn)",
            },
            {
                "Chỉ số": "ROA (Return on Assets)",
                "Công thức": "Lợi nhuận sau thuế / Tổng tài sản",
                "Dữ liệu còn thiếu": "Lợi nhuận ròng + Tổng tài sản (bảng cân đối kế toán)",
            },
            {
                "Chỉ số": "ROE (Return on Equity)",
                "Công thức": "Lợi nhuận sau thuế / Vốn chủ sở hữu",
                "Dữ liệu còn thiếu": "Lợi nhuận ròng + Vốn chủ sở hữu (bảng cân đối kế toán)",
            },
        ]
    )
    st.dataframe(missing_metrics, use_container_width=True, hide_index=True)

    st.caption(
        "ℹ️ Nếu có thêm bảng dạng `fact_finance` / `dim_account` (tài sản, nợ, vốn chủ sở hữu, chi phí vận hành, "
        "thuế TNDN, số dư tiền mặt theo kỳ), mình có thể bổ sung tính toán đầy đủ các chỉ số này ở trang này."
    )