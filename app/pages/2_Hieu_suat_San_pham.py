"""
2_Hieu_suat_San_pham.py — Phân tích Hiệu suất Sản phẩm
Nguồn: fact_product_daily · dim_product (SCD2) · fact_inventory
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

# Sau
params = {"start_date": start_date, "end_date": end_date}

st.title("📦 Hiệu suất Sản phẩm")
st.caption("Nguồn dữ liệu: `fact_product_daily` · `dim_product` (SCD2) · `fact_inventory`")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "🏆 Top/Bottom & Danh mục",
        "📐 Biên lợi nhuận",
        "📉 Snapshot giá theo ngày",
        "🔀 Tác động đổi giá",
        "🧪 Kiểm định ABC & Vận hành kho",
    ]
)

# ----------------------------------------------------------------------------
# Dữ liệu gốc dùng chung cho tab 1, 2 & 5
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
<<<<<<< HEAD
=======
      AND dp.product_name != 'UNKNOWN'
>>>>>>> origin/develop
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
    q_names = "SELECT DISTINCT product_id, product_name FROM dim_product ORDER BY product_name"
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
    q_names2 = "SELECT DISTINCT product_id, product_name FROM dim_product ORDER BY product_name"
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
# TAB 5 — Kiểm định: ABC doanh thu, nghịch lý biên lợi nhuận & vận hành kho
# ==============================================================================
with tab5:
    st.subheader("🧪 Kiểm định các nhận định về cơ cấu doanh thu, lợi nhuận & tồn kho")

    if df_prod.empty:
        st.info("Không có dữ liệu trong khoảng thời gian đã chọn.")
    else:
        # ------------------------------------------------------------------
        # 1) Kiểm định phân tích ABC (Pareto doanh thu)
        # ------------------------------------------------------------------
        st.markdown("### 1️⃣ Kiểm định phân tích ABC (Pareto doanh thu)")

        with st.expander("ℹ️ Nhóm A/B/C là gì?", expanded=True):
            st.markdown(
                "Phân loại theo nguyên tắc Pareto (80/20), xếp sản phẩm theo doanh thu giảm dần rồi cộng dồn:\n"
                "- **Nhóm A — Sản phẩm chủ lực:** cộng dồn đến **≤ 80%** tổng doanh thu. Ít sản phẩm nhưng đóng góp doanh thu áp đảo, cần ưu tiên quản lý sát nhất.\n"
                "- **Nhóm B — Sản phẩm trung bình:** phần cộng dồn từ **> 80% đến 95%**. Đóng góp vừa phải, theo dõi ở mức trung bình.\n"
                "- **Nhóm C — Sản phẩm đuôi dài (long-tail):** phần cộng dồn còn lại **> 95% đến 100%**. Số lượng sản phẩm lớn nhưng mỗi sản phẩm đóng góp doanh thu rất nhỏ, dễ bị chôn vốn nếu không kiểm soát tồn kho tốt."
            )

        df_abc = df_prod.sort_values("total_revenue", ascending=False).reset_index(drop=True)
        total_rev_all = df_abc["total_revenue"].sum()
        df_abc["cum_revenue"] = df_abc["total_revenue"].cumsum()
        df_abc["cum_pct"] = df_abc["cum_revenue"] / total_rev_all * 100
        df_abc["rank"] = df_abc.index + 1

        def _classify_abc(p):
            if p <= 80:
                return "A"
            elif p <= 95:
                return "B"
            return "C"

        df_abc["abc_group"] = df_abc["cum_pct"].apply(_classify_abc)

        abc_summary = (
            df_abc.groupby("abc_group")
            .agg(so_sp=("product_id", "nunique"), doanh_thu=("total_revenue", "sum"), ln_gop=("total_gross_profit", "sum"))
            .reindex(["A", "B", "C"])
            .fillna(0)
        )
        abc_summary["ty_le_sp_pct"] = abc_summary["so_sp"] / abc_summary["so_sp"].sum() * 100
        abc_summary["ty_le_dt_pct"] = abc_summary["doanh_thu"] / abc_summary["doanh_thu"].sum() * 100
        abc_summary["bien_ln_pct"] = abc_summary["ln_gop"] / abc_summary["doanh_thu"].replace(0, pd.NA) * 100

        c1, c2, c3 = st.columns(3)
        for col, grp in zip([c1, c2, c3], ["A", "B", "C"]):
            row = abc_summary.loc[grp]
            col.metric(
                f"Nhóm {grp} · {int(row['so_sp'])} SP ({row['ty_le_sp_pct']:.1f}% danh mục)",
                f"{row['ty_le_dt_pct']:.1f}% doanh thu",
                f"Biên LN gộp {row['bien_ln_pct']:.1f}%" if pd.notna(row["bien_ln_pct"]) else "—",
            )

        fig_pareto = make_subplots(specs=[[{"secondary_y": True}]])
        fig_pareto.add_trace(
            go.Bar(
                x=df_abc["rank"], y=df_abc["total_revenue"], name="Doanh thu SP",
                marker_color=df_abc["abc_group"].map({"A": "#10b981", "B": "#f59e0b", "C": "#ef4444"}),
            ),
            secondary_y=False,
        )
        fig_pareto.add_trace(
            go.Scatter(x=df_abc["rank"], y=df_abc["cum_pct"], name="% Doanh thu tích lũy", line=dict(color="#6366f1", width=2)),
            secondary_y=True,
        )
        fig_pareto.add_hline(y=80, line_dash="dash", line_color="#6366f1", secondary_y=True, annotation_text="Ngưỡng 80%")
        fig_pareto.update_layout(
            title="Biểu đồ Pareto — Doanh thu theo sản phẩm (xanh = A, vàng = B, đỏ = C)", height=450,
            legend=dict(orientation="h", y=1.12),
        )
        fig_pareto.update_yaxes(title_text="Doanh thu", secondary_y=False)
        fig_pareto.update_yaxes(title_text="% tích lũy", secondary_y=True, range=[0, 105])
        st.plotly_chart(fig_pareto, use_container_width=True)

        grp_a_cat = df_abc[df_abc["abc_group"] == "A"].groupby("category_name", as_index=False)["total_revenue"].sum()
        if not grp_a_cat.empty:
            grp_a_cat["ty_le_pct"] = grp_a_cat["total_revenue"] / grp_a_cat["total_revenue"].sum() * 100
            grp_a_cat = grp_a_cat.sort_values("ty_le_pct", ascending=False)
            top_cat_a = grp_a_cat.iloc[0]
            st.caption(
                f"ℹ️ Trong nhóm A, danh mục **{top_cat_a['category_name']}** chiếm "
                f"**{top_cat_a['ty_le_pct']:.1f}%** doanh thu của nhóm A — xác nhận mức độ tập trung doanh thu "
                f"vào một nhóm sản phẩm chủ lực."
            )
            st.dataframe(
                grp_a_cat.rename(columns={"category_name": "Danh mục", "total_revenue": "Doanh thu", "ty_le_pct": "% trong nhóm A"})
                .style.format({"Doanh thu": "{:,.0f}", "% trong nhóm A": "{:,.1f}%"}),
                use_container_width=True, hide_index=True,
            )

        st.divider()

        # ------------------------------------------------------------------
        # 2) Kiểm định nghịch lý Doanh thu – Biên lợi nhuận theo danh mục
        # ------------------------------------------------------------------
        st.markdown("### 2️⃣ Kiểm định nghịch lý Doanh thu – Biên lợi nhuận theo danh mục")

        cat_valid = (
            df_prod.groupby("category_name", as_index=False)
            .agg(revenue=("total_revenue", "sum"), gross_profit=("total_gross_profit", "sum"), qty=("total_qty", "sum"))
        )
        cat_valid["revenue_share_pct"] = cat_valid["revenue"] / cat_valid["revenue"].sum() * 100
        cat_valid["margin_pct"] = cat_valid["gross_profit"] / cat_valid["revenue"].replace(0, pd.NA) * 100
        cat_valid = cat_valid.sort_values("revenue_share_pct", ascending=False)

        fig_quad = px.scatter(
            cat_valid, x="revenue_share_pct", y="margin_pct", size="revenue", text="category_name",
            title="Ma trận Tỷ trọng doanh thu vs Biên lợi nhuận theo danh mục",
            labels={"revenue_share_pct": "% Tỷ trọng doanh thu", "margin_pct": "Biên LN gộp (%)"},
        )
        fig_quad.update_traces(textposition="top center")
        fig_quad.add_vline(x=cat_valid["revenue_share_pct"].mean(), line_dash="dot", line_color="gray")
        fig_quad.add_hline(y=cat_valid["margin_pct"].mean(), line_dash="dot", line_color="gray")
        fig_quad.update_layout(height=450)
        st.plotly_chart(fig_quad, use_container_width=True)

        show_cat = cat_valid.rename(
            columns={
                "category_name": "Danh mục", "revenue": "Doanh thu", "gross_profit": "LN gộp",
                "qty": "Số lượng bán", "revenue_share_pct": "% Tỷ trọng DT", "margin_pct": "Biên LN gộp (%)",
            }
        )
        st.dataframe(
            show_cat.style.format(
                {"Doanh thu": "{:,.0f}", "LN gộp": "{:,.0f}", "% Tỷ trọng DT": "{:,.1f}%", "Biên LN gộp (%)": "{:,.1f}%"}
            ),
            use_container_width=True, hide_index=True,
        )

        # Kiểm định tương quan (cấp sản phẩm) giữa doanh thu và biên lợi nhuận
        valid_corr = df_prod.dropna(subset=["gross_margin_pct", "total_revenue"])
        corr, pval = None, None
        if len(valid_corr) >= 3:
            try:
                from scipy.stats import pearsonr
                corr, pval = pearsonr(valid_corr["total_revenue"].astype(float), valid_corr["gross_margin_pct"].astype(float))
            except ImportError:
                corr = valid_corr["total_revenue"].corr(valid_corr["gross_margin_pct"])
                pval = None

        if corr is not None:
            direction = "nghịch (âm)" if corr < 0 else "thuận (dương)"
            strength = "yếu" if abs(corr) < 0.3 else ("trung bình" if abs(corr) < 0.6 else "mạnh")
            conclusion = (
                "→ ủng hộ nhận định: doanh thu cao **không** đồng nghĩa biên lợi nhuận cao."
                if corr < 0
                else "→ dữ liệu hiện tại **chưa** cho thấy nghịch lý rõ rệt giữa doanh thu và biên lợi nhuận ở cấp sản phẩm."
            )
            pval_txt = f", p-value = {pval:.4f}" if pval is not None else " (tương quan Pearson, không có p-value do scipy chưa cài đặt)"
            st.info(
                f"📊 **Kiểm định tương quan Pearson** giữa Doanh thu và Biên LN gộp (cấp sản phẩm): "
                f"r = **{corr:.2f}**{pval_txt} → tương quan {direction}, mức độ {strength}. {conclusion}"
            )

        st.divider()

        # ------------------------------------------------------------------
        # 3) Kiểm định vận hành kho
        # ------------------------------------------------------------------
        st.markdown("### 3️⃣ Kiểm định vận hành kho — Vòng quay tồn kho theo danh mục")

        q_inventory = """
            SELECT dp.product_id, dp.product_name, dp.category_name, dp.subcategory_name,
                   SUM(fi.quantity) AS ton_kho
            FROM fact_inventory fi
            JOIN dim_product dp ON fi.product_key = dp.product_key
            WHERE dp.is_current = TRUE
            GROUP BY dp.product_id, dp.product_name, dp.category_name, dp.subcategory_name
        """
        df_inv = run_query(q_inventory)

        if df_inv.empty:
            st.info("Chưa có dữ liệu tồn kho (`fact_inventory`) để kiểm định phần vận hành kho.")
        else:
            days_in_range = max((end_date - start_date).days + 1, 1)

            df_inv_merge = df_inv.merge(df_prod[["product_id", "total_qty"]], on="product_id", how="left")
            df_inv_merge["total_qty"] = df_inv_merge["total_qty"].fillna(0)
            df_inv_merge["avg_daily_qty"] = df_inv_merge["total_qty"] / days_in_range
            df_inv_merge["days_of_supply"] = df_inv_merge.apply(
                lambda r: (r["ton_kho"] / r["avg_daily_qty"]) if r["avg_daily_qty"] > 0 else None, axis=1
            )

            c1, c2 = st.columns(2)
            with c1:
                stockout_th = st.slider("Ngưỡng nguy cơ thiếu hàng — số ngày tồn kho <", 1, 30, 14, key="stockout_th")
            with c2:
                excess_th = st.slider("Ngưỡng tồn kho ứ đọng — số ngày tồn kho >", 30, 365, 90, key="excess_th")

            def _classify_inv(row):
                if row["avg_daily_qty"] == 0 or pd.isna(row["days_of_supply"]):
                    return "⚪ Không phát sinh bán trong kỳ"
                elif row["days_of_supply"] < stockout_th:
                    return "⚠️ Nguy cơ thiếu hàng"
                elif row["days_of_supply"] > excess_th:
                    return "🐢 Tồn kho ứ đọng (chôn vốn)"
                return "✅ Bình thường"

            df_inv_merge["trang_thai"] = df_inv_merge.apply(_classify_inv, axis=1)

            risk_by_cat = df_inv_merge.groupby(["category_name", "trang_thai"], as_index=False).agg(so_sp=("product_id", "nunique"))
            fig_risk = px.bar(
                risk_by_cat, x="category_name", y="so_sp", color="trang_thai", barmode="stack",
                title="Phân bổ trạng thái tồn kho theo danh mục",
                labels={"category_name": "Danh mục", "so_sp": "Số sản phẩm", "trang_thai": "Trạng thái"},
                color_discrete_map={
                    "✅ Bình thường": "#10b981",
                    "⚠️ Nguy cơ thiếu hàng": "#ef4444",
                    "🐢 Tồn kho ứ đọng (chôn vốn)": "#f59e0b",
                    "⚪ Không phát sinh bán trong kỳ": "#9ca3af",
                },
            )
            fig_risk.update_layout(height=450)
            st.plotly_chart(fig_risk, use_container_width=True)

            tcol1, tcol2 = st.columns(2)
            with tcol1:
                st.caption("🐢 Top tồn kho ứ đọng (ứng viên chương trình xả hàng)")
                excess_df = df_inv_merge[df_inv_merge["trang_thai"] == "🐢 Tồn kho ứ đọng (chôn vốn)"].nlargest(10, "days_of_supply")
                st.dataframe(
                    excess_df[["product_name", "category_name", "ton_kho", "avg_daily_qty", "days_of_supply"]]
                    .rename(columns={"product_name": "Sản phẩm", "category_name": "Danh mục", "ton_kho": "Tồn kho",
                                      "avg_daily_qty": "SL bán TB/ngày", "days_of_supply": "Ngày tồn kho"})
                    .style.format({"SL bán TB/ngày": "{:,.2f}", "Ngày tồn kho": "{:,.0f}"}),
                    use_container_width=True, hide_index=True,
                )
            with tcol2:
                st.caption("⚠️ Top nguy cơ thiếu hàng (ứng viên bổ sung gấp)")
                risk_df = df_inv_merge[df_inv_merge["trang_thai"] == "⚠️ Nguy cơ thiếu hàng"].nsmallest(10, "days_of_supply")
                st.dataframe(
                    risk_df[["product_name", "category_name", "ton_kho", "avg_daily_qty", "days_of_supply"]]
                    .rename(columns={"product_name": "Sản phẩm", "category_name": "Danh mục", "ton_kho": "Tồn kho",
                                      "avg_daily_qty": "SL bán TB/ngày", "days_of_supply": "Ngày tồn kho"})
                    .style.format({"SL bán TB/ngày": "{:,.2f}", "Ngày tồn kho": "{:,.0f}"}),
                    use_container_width=True, hide_index=True,
                )

            st.caption(
                "ℹ️ *Phương pháp:* `fact_inventory` là ảnh chụp tồn kho hiện tại (không có `date_key`), nên không thể tách theo "
                "khoảng thời gian đã chọn. Do dữ liệu không có sẵn cột an toàn kho / điểm đặt hàng lại, trạng thái tồn kho được "
                "ước lượng bằng **Ngày tồn kho (Days of Supply) = Tồn kho hiện tại / Tốc độ bán trung bình mỗi ngày** trong "
                "khoảng thời gian đã chọn ở thanh bên. Ngưỡng phân loại có thể điều chỉnh bằng 2 thanh trượt phía trên."
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
GROUP BY dp.product_id, dp.product_name, dp.category_name;""",
        language="sql",
    )
    st.markdown(
        "**Lưu ý:** `dim_product` là SCD2 nên `product_id` có thể có nhiều `product_key` "
        "(mỗi lần đổi giá = 1 phiên bản). Luôn `GROUP BY product_id` (không phải `product_key`) "
        "khi muốn gộp doanh số của cùng 1 sản phẩm qua các đợt đổi giá."
    )
    st.code(
        """-- Ngày tồn kho (Days of Supply) theo sản phẩm
SELECT dp.product_id, dp.product_name,
       SUM(fi.quantity) AS ton_kho,
       SUM(fpd.quantity_sold) / :so_ngay AS sl_ban_tb_ngay,
       SUM(fi.quantity) / NULLIF(SUM(fpd.quantity_sold) / :so_ngay, 0) AS ngay_ton_kho
FROM fact_inventory fi
JOIN dim_product dp ON fi.product_key = dp.product_key AND dp.is_current = TRUE
LEFT JOIN fact_product_daily fpd ON fpd.product_key = dp.product_key
GROUP BY dp.product_id, dp.product_name;""",
        language="sql",
    )
