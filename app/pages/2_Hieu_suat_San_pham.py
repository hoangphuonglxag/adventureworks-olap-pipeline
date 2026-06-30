"""
2_Hieu_suat_San_pham.py — Phân tích Hiệu suất Sản phẩm
Nguồn: fact_product_daily · dim_product (SCD2)
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
from utils.helpers import normalize_date_range

st.set_page_config(page_title="Hiệu suất Sản phẩm", page_icon="📦", layout="wide")
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

params = {"start_date": start_date, "end_date": end_date}

st.title("📦 Hiệu suất Sản phẩm")
st.caption("Nguồn dữ liệu: `fact_product_daily` · `dim_product` (SCD2)")

tab1, tab2, tab3, tab4 = st.tabs(
    ["🏆 Top/Bottom & Danh mục", "📐 Biên lợi nhuận", "📉 Snapshot giá theo ngày", "🔀 Tác động đổi giá"]
)

# ----------------------------------------------------------------------------
# Dữ liệu gốc dùng chung cho tab 1 & 2
# ----------------------------------------------------------------------------
q_products = """
    SELECT dp.product_id, dp.product_name, dp.category_name, dp.subcategory_name,
           SUM(fpd.quantity_sold)  AS total_qty,
           SUM(fpd.revenue)        AS total_revenue,
           SUM(fpd.gross_profit)   AS total_gross_profit,
           SUM(fpd.order_count)    AS total_orders
    FROM fact_product_daily fpd
    JOIN dim_product dp ON fpd.product_key = dp.product_key
    JOIN dim_date d ON fpd.date_key = d.date_key
    WHERE d.full_date BETWEEN :start_date AND :end_date
      AND dp.product_name != 'UNKNOWN'
    GROUP BY dp.product_id, dp.product_name, dp.category_name, dp.subcategory_name
"""
df_prod = run_query(q_products, params)
if not df_prod.empty:
    df_prod["gross_margin_pct"] = df_prod["total_gross_profit"] / df_prod["total_revenue"].replace(0, pd.NA) * 100

# ==============================================================================
# TAB 1 — Top/Bottom sản phẩm & Danh mục
# ==============================================================================
with tab1:
    if df_prod.empty:
        st.info("Không có dữ liệu trong khoảng thời gian đã chọn.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("📦 Số sản phẩm có doanh số", fmt_num(df_prod["product_id"].nunique()))
        c2.metric("💰 Tổng doanh thu", fmt_num(df_prod["total_revenue"].sum()))
        overall_margin = safe_div(df_prod["total_gross_profit"].sum(), df_prod["total_revenue"].sum())
        c3.metric("📐 Biên LN gộp TB", fmt_pct(overall_margin * 100 if overall_margin is not None else None))

        c1, c2 = st.columns(2)
        with c1:
            metric_choice = st.selectbox("Xếp hạng theo", ["Doanh thu", "Số lượng bán", "Biên lợi nhuận gộp"], key="rank_metric")
        with c2:
            top_n = st.slider("Số lượng hiển thị (Top N)", 5, 30, 10)

        metric_map = {"Doanh thu": "total_revenue", "Số lượng bán": "total_qty", "Biên lợi nhuận gộp": "gross_margin_pct"}
        mcol = metric_map[metric_choice]

        col_top, col_bottom = st.columns(2)
        with col_top:
            top_df = df_prod.nlargest(top_n, mcol)
            fig_top = px.bar(
                top_df.sort_values(mcol), x=mcol, y="product_name", orientation="h",
                title=f"🏆 Top {top_n} sản phẩm — {metric_choice}",
                color_discrete_sequence=["#10b981"],
            )
            fig_top.update_layout(height=max(350, 28 * top_n))
            st.plotly_chart(fig_top, use_container_width=True)
        with col_bottom:
            bottom_df = df_prod.nsmallest(top_n, mcol)
            fig_bottom = px.bar(
                bottom_df.sort_values(mcol), x=mcol, y="product_name", orientation="h",
                title=f"⬇️ Bottom {top_n} sản phẩm — {metric_choice}",
                color_discrete_sequence=["#ef4444"],
            )
            fig_bottom.update_layout(height=max(350, 28 * top_n))
            st.plotly_chart(fig_bottom, use_container_width=True)

        st.divider()
        st.markdown("**Hiệu suất theo danh mục / phân danh mục**")
        fig_tree = px.treemap(
            df_prod, path=[px.Constant("Tất cả"), "category_name", "subcategory_name", "product_name"],
            values="total_revenue", color="gross_margin_pct",
            color_continuous_scale="RdYlGn", title="Treemap doanh thu theo Danh mục → Phân danh mục → Sản phẩm",
        )
        fig_tree.update_layout(height=500)
        st.plotly_chart(fig_tree, use_container_width=True)

        cat_agg = (
            df_prod.groupby("category_name", as_index=False)
            .agg(revenue=("total_revenue", "sum"), qty=("total_qty", "sum"), gross_profit=("total_gross_profit", "sum"))
        )
        cat_agg["margin_pct"] = cat_agg["gross_profit"] / cat_agg["revenue"].replace(0, pd.NA) * 100
        fig_cat = px.bar(
            cat_agg.sort_values("revenue", ascending=True), x="revenue", y="category_name", orientation="h",
            title="Doanh thu theo danh mục", color_discrete_sequence=["#6366f1"],
        )
        st.plotly_chart(fig_cat, use_container_width=True)

# ==============================================================================
# TAB 2 — Biên lợi nhuận gộp
# ==============================================================================
with tab2:
    if df_prod.empty:
        st.info("Không có dữ liệu trong khoảng thời gian đã chọn.")
    else:
        fig_scatter = px.scatter(
            df_prod, x="total_revenue", y="gross_margin_pct", size="total_qty", color="category_name",
            hover_name="product_name", title="Doanh thu vs Biên lợi nhuận gộp theo sản phẩm",
            labels={"total_revenue": "Doanh thu", "gross_margin_pct": "Biên LN gộp (%)"},
        )
        fig_scatter.update_layout(height=500)
        st.plotly_chart(fig_scatter, use_container_width=True)

        st.markdown("**Bảng chi tiết biên lợi nhuận theo sản phẩm**")
        show = df_prod[["product_name", "category_name", "subcategory_name", "total_revenue", "total_gross_profit", "gross_margin_pct"]].copy()
        show.columns = ["Sản phẩm", "Danh mục", "Phân danh mục", "Doanh thu", "LN gộp", "Biên LN gộp (%)"]
        st.dataframe(
            show.sort_values("Biên LN gộp (%)", ascending=False).style.format(
                {"Doanh thu": "{:,.0f}", "LN gộp": "{:,.0f}", "Biên LN gộp (%)": "{:,.1f}%"}
            ),
            use_container_width=True, hide_index=True, height=400,
        )

# ==============================================================================
# TAB 3 — Snapshot giá vốn / giá niêm yết theo ngày
# ==============================================================================
with tab3:
    q_names = "SELECT DISTINCT product_id, product_name FROM dim_product WHERE product_name != 'UNKNOWN' ORDER BY product_name"
    df_names = run_query(q_names)

    if df_names.empty:
        st.info("Chưa có dữ liệu sản phẩm.")
    else:
        selected_name = st.selectbox("Chọn sản phẩm", df_names["product_name"].tolist(), key="snap_product")
        product_id = int(df_names.loc[df_names["product_name"] == selected_name, "product_id"].iloc[0])

        q_snap = """
            SELECT d.full_date, fpd.avg_standard_cost, fpd.avg_list_price,
                   fpd.revenue, fpd.quantity_sold, fpd.gross_profit
            FROM fact_product_daily fpd
            JOIN dim_product dp ON fpd.product_key = dp.product_key
            JOIN dim_date d ON fpd.date_key = d.date_key
            WHERE dp.product_id = :product_id AND d.full_date BETWEEN :start_date AND :end_date
            ORDER BY d.full_date
        """
        df_snap = run_query(q_snap, {"product_id": product_id, **params})

        if df_snap.empty:
            st.info(f"Không có dữ liệu bán hàng cho sản phẩm **{selected_name}** trong khoảng thời gian đã chọn.")
        else:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Scatter(x=df_snap["full_date"], y=df_snap["avg_list_price"], name="Giá niêm yết", line=dict(color="#f59e0b")),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(x=df_snap["full_date"], y=df_snap["avg_standard_cost"], name="Giá vốn", line=dict(color="#ef4444")),
                secondary_y=False,
            )
            fig.add_trace(
                go.Bar(x=df_snap["full_date"], y=df_snap["quantity_sold"], name="Số lượng bán", marker_color="rgba(99,102,241,0.35)"),
                secondary_y=True,
            )
            fig.update_layout(title=f"Snapshot giá & số lượng bán — {selected_name}", height=450, legend=dict(orientation="h", y=1.12))
            fig.update_yaxes(title_text="Giá", secondary_y=False)
            fig.update_yaxes(title_text="Số lượng bán", secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

            c1, c2, c3 = st.columns(3)
            c1.metric("💰 Tổng doanh thu", fmt_num(df_snap["revenue"].sum()))
            c2.metric("📦 Tổng số lượng", fmt_num(df_snap["quantity_sold"].sum()))
            c3.metric("📐 Tổng LN gộp", fmt_num(df_snap["gross_profit"].sum()))

# ==============================================================================
# TAB 4 — Tác động thay đổi giá đến doanh số (SCD2 versions)
# ==============================================================================
with tab4:
    q_names2 = "SELECT DISTINCT product_id, product_name FROM dim_product WHERE product_name != 'UNKNOWN' ORDER BY product_name"
    df_names2 = run_query(q_names2)

    if df_names2.empty:
        st.info("Chưa có dữ liệu sản phẩm.")
    else:
        selected_name2 = st.selectbox("Chọn sản phẩm", df_names2["product_name"].tolist(), key="impact_product")
        product_id2 = int(df_names2.loc[df_names2["product_name"] == selected_name2, "product_id"].iloc[0])

        q_versions = """
            SELECT dp.version, dp.effective_date, dp.expiry_date, dp.is_current,
                   dp.standard_cost, dp.list_price,
                   COALESCE(SUM(fpd.quantity_sold), 0)  AS total_qty,
                   COALESCE(SUM(fpd.revenue), 0)         AS total_revenue,
                   COALESCE(AVG(fpd.quantity_sold), 0)   AS avg_daily_qty,
                   COUNT(fpd.fact_product_daily_key)     AS days_with_sales
            FROM dim_product dp
            LEFT JOIN fact_product_daily fpd ON fpd.product_key = dp.product_key
            WHERE dp.product_id = :product_id
            GROUP BY dp.version, dp.effective_date, dp.expiry_date, dp.is_current, dp.standard_cost, dp.list_price
            ORDER BY dp.version
        """
        df_ver = run_query(q_versions, {"product_id": product_id2})

        if df_ver.empty:
            st.info("Không có lịch sử phiên bản giá cho sản phẩm này.")
        elif len(df_ver) == 1:
            st.info(f"Sản phẩm **{selected_name2}** chưa từng thay đổi giá (chỉ có 1 phiên bản).")
            st.dataframe(df_ver, use_container_width=True, hide_index=True)
        else:
            df_ver["version_label"] = "v" + df_ver["version"].astype(str) + " (" + df_ver["effective_date"].astype(str) + ")"

            fig_impact = make_subplots(specs=[[{"secondary_y": True}]])
            fig_impact.add_trace(
                go.Bar(x=df_ver["version_label"], y=df_ver["avg_daily_qty"], name="SL bán TB/ngày", marker_color="#6366f1"),
                secondary_y=False,
            )
            fig_impact.add_trace(
                go.Scatter(x=df_ver["version_label"], y=df_ver["list_price"], name="Giá niêm yết", line=dict(color="#f59e0b", width=3)),
                secondary_y=True,
            )
            fig_impact.update_layout(title=f"Tác động thay đổi giá đến doanh số — {selected_name2}", height=450)
            fig_impact.update_yaxes(title_text="SL bán TB/ngày", secondary_y=False)
            fig_impact.update_yaxes(title_text="Giá niêm yết", secondary_y=True)
            st.plotly_chart(fig_impact, use_container_width=True)

            show_ver = df_ver[["version", "effective_date", "expiry_date", "is_current", "standard_cost", "list_price", "total_qty", "total_revenue", "avg_daily_qty"]].copy()
            show_ver.columns = ["Phiên bản", "Hiệu lực từ", "Hết hiệu lực", "Đang dùng", "Giá vốn", "Giá niêm yết", "Tổng SL bán", "Tổng doanh thu", "SL bán TB/ngày"]
            st.dataframe(show_ver, use_container_width=True, hide_index=True)
            st.caption(
                "ℹ️ Mỗi dòng = 1 phiên bản giá (SCD2) của sản phẩm. So sánh `SL bán TB/ngày` "
                "giữa các phiên bản để đánh giá độ co giãn theo giá (price elasticity)."
            )

# ==============================================================================
# Gợi ý SQL
# ==============================================================================
with st.expander("🧠 Gợi ý SQL"):
    st.code(
        """SELECT dp.product_id, dp.product_name, dp.category_name,
       SUM(fpd.revenue) AS total_revenue,
       SUM(fpd.gross_profit) AS total_gross_profit
FROM fact_product_daily fpd
JOIN dim_product dp ON fpd.product_key = dp.product_key
JOIN dim_date d ON fpd.date_key = d.date_key
WHERE d.full_date BETWEEN :start_date AND :end_date
  AND dp.product_name != 'UNKNOWN'
GROUP BY dp.product_id, dp.product_name, dp.category_name;""",
        language="sql",
    )
    st.markdown(
        "**Lưu ý:** `dim_product` là SCD2 nên `product_id` có thể có nhiều `product_key` "
        "(mỗi lần đổi giá = 1 phiên bản). Luôn `GROUP BY product_id` (không phải `product_key`) "
        "khi muốn gộp doanh số của cùng 1 sản phẩm qua các đợt đổi giá."
    )
