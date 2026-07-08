"""
4_Hieu_suat_Nhan_vien.py — Phân tích Hiệu suất Nhân viên bán
Nguồn: fact_seller_daily · dim_seller (SCD2)
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scipy.stats import mannwhitneyu
import numpy as np
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

tab1, tab2, tab3, tab4 = st.tabs([
    "🏆 Leaderboard & Doanh thu", "🎯 Quota Attainment", "📜 Lịch sử Quota/Bonus (SCD2)",
    "🧪 Kiểm định giả thuyết",
])

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
# TAB 4 — Kiểm định giả thuyết (Tập trung doanh thu & Key Person Risk)
# ==============================================================================
with tab4:
    # ---------- Phần A: Mức độ tập trung doanh thu ----------
        st.subheader("A. Mức độ tập trung doanh thu (Top Performer & Gini)")

        df_sorted = (
            df_sellers.sort_values("total_revenue", ascending=False)
            .reset_index(drop=True)
        )

        total_rev = df_sorted["total_revenue"].sum()
        n_sellers = len(df_sorted)


        def revenue_share_top_n(n):
            n = min(n, n_sellers)
            return df_sorted.head(n)["total_revenue"].sum() / total_rev * 100


        def gini_coefficient(values):
            arr = np.sort(np.array(values, dtype=float))
            n = len(arr)
            if n == 0 or arr.sum() == 0:
                return None

            idx = np.arange(1, n + 1)
            return (2 * np.sum(idx * arr) - (n + 1) * np.sum(arr)) / (n * np.sum(arr))


        # =============================
        # Các chỉ số
        # =============================
        cr3 = revenue_share_top_n(3)
        cr4 = revenue_share_top_n(4)
        cr5 = revenue_share_top_n(5)

        gini = gini_coefficient(df_sorted["total_revenue"])

        top4 = df_sorted.head(4)
        rest = df_sorted.iloc[4:]

        top4_pct = top4["total_revenue"].sum() / total_rev * 100
        rest_pct = 100 - top4_pct

        top4_avg = top4["total_revenue"].mean()

        if len(rest) > 0:
            rest_avg = rest["total_revenue"].mean()
            ratio = top4_avg / rest_avg
        else:
            rest_avg = np.nan
            ratio = np.nan

        # =============================
        # Metrics
        # =============================
        c1, c2, c3, c4, c5 = st.columns(5)

        c1.metric("Top 3 / Tổng DT", f"{cr3:.1f}%")
        c2.metric("Top 4 / Tổng DT", f"{cr4:.1f}%")
        c3.metric("Top 5 / Tổng DT", f"{cr5:.1f}%")
        c4.metric(
            "Top 4 / Còn lại",
            f"{top4_pct:.1f}% : {rest_pct:.1f}%"
        )
        c5.metric(
            "Gini",
            f"{gini:.2f}" if gini is not None else "N/A"
        )

        # =============================
        # So sánh doanh thu bình quân
        # =============================
        st.markdown("### So sánh doanh thu bình quân")

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Top 4",
            f"{top4_avg:,.0f}"
        )

        c2.metric(
            "Nhân viên còn lại",
            f"{rest_avg:,.0f}" if not np.isnan(rest_avg) else "N/A"
        )

        c3.metric(
            "Top 4 cao hơn",
            f"{ratio:.2f} lần" if not np.isnan(ratio) else "N/A"
        )

        # =============================
        # Mann–Whitney U Test
        # =============================
        if len(rest) >= 2:

            stat, p = mannwhitneyu(
                top4["total_revenue"],
                rest["total_revenue"],
                alternative="greater"
            )

            st.markdown("### Kiểm định Mann–Whitney U")

            st.write(f"**U statistic:** {stat:.2f}")
            st.write(f"**p-value:** {p:.4f}")

            if p < 0.05:
                st.success(
                    "✅ Doanh thu của nhóm 4 nhân viên dẫn đầu cao hơn nhóm còn lại "
                    "một cách có ý nghĩa thống kê (p < 0.05). "
                    "Điều này cho thấy doanh thu có xu hướng phụ thuộc vào một nhóm nhỏ nhân viên chủ lực."
                )
            else:
                st.warning(
                    "⚠️ Chưa có đủ bằng chứng thống kê (p ≥ 0.05) để kết luận "
                    "4 nhân viên dẫn đầu vượt trội so với nhóm còn lại."
                )

        # =============================
        # Lorenz Curve
        # =============================
        df_sorted["cum_revenue_pct"] = (
            df_sorted["total_revenue"].cumsum()
            / total_rev
            * 100
        )

        df_sorted["cum_seller_pct"] = (
            (df_sorted.index + 1)
            / n_sellers
            * 100
        )

        fig = px.line(
            df_sorted,
            x="cum_seller_pct",
            y="cum_revenue_pct",
            markers=True,
            title="Đường cong Lorenz - Mức độ tập trung doanh thu",
            labels={
                "cum_seller_pct": "% Nhân viên tích lũy",
                "cum_revenue_pct": "% Doanh thu tích lũy",
            },
        )

        fig.add_shape(
            type="line",
            x0=0,
            y0=0,
            x1=100,
            y1=100,
            line=dict(color="gray", dash="dash")
        )

        fig.update_layout(
            xaxis_range=[0, 100],
            yaxis_range=[0, 100]
        )

        st.plotly_chart(fig, use_container_width=True)

        # ---------- Phần B: Top Performer vs Phần còn lại ----------
        st.subheader("B. So sánh Top Performer vs. Phần còn lại (tỷ lệ đạt quota)")

        top_pct = st.slider("Ngưỡng Top Performer (% nhân viên đứng đầu theo doanh thu)", 5, 50, 20, key="top_pct_slider")
        n_top = max(1, round(n_sellers * top_pct / 100))
        top_ids = df_sorted.head(n_top)["seller_id"]
        df_sellers["group"] = df_sellers["seller_id"].apply(lambda x: "Top performer" if x in top_ids.values else "Còn lại")

        grp_summary = df_sellers.groupby("group").agg(
            so_nv=("seller_id", "count"),
            dt_tb=("total_revenue", "mean"),
            attainment_tb=("quota_attainment_pct", "mean"),
            ty_le_dat_quota=("quota_attainment_pct", lambda s: (s >= 100).mean() * 100),
        ).reindex(["Top performer", "Còn lại"])
        grp_summary.columns = ["Số nhân viên", "DT trung bình", "% Đạt quota (TB)", "% NV đạt/vượt quota"]

        st.dataframe(
            grp_summary.style.format({"DT trung bình": "{:,.0f}", "% Đạt quota (TB)": "{:,.1f}%", "% NV đạt/vượt quota": "{:,.1f}%"}),
            use_container_width=True,
        )

        # Welch's t-test thủ công (không phụ thuộc scipy) so sánh % đạt quota giữa 2 nhóm
        a = df_sellers.loc[df_sellers["group"] == "Top performer", "quota_attainment_pct"].dropna()
        b = df_sellers.loc[df_sellers["group"] == "Còn lại", "quota_attainment_pct"].dropna()

        if len(a) >= 2 and len(b) >= 2:
            mean_a, mean_b = a.mean(), b.mean()
            var_a, var_b = a.var(ddof=1), b.var(ddof=1)
            n_a, n_b = len(a), len(b)
            se = ((var_a / n_a) + (var_b / n_b)) ** 0.5
            t_stat = (mean_a - mean_b) / se if se > 0 else float("nan")
            df_welch = (
                ((var_a / n_a) + (var_b / n_b)) ** 2
                / ((var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1))
            ) if n_a > 1 and n_b > 1 else float("nan")

            st.caption(
                f"**Kiểm định Welch t-test** — % đạt quota: Top performer (n={n_a}, TB={mean_a:.1f}%) "
                f"vs Còn lại (n={n_b}, TB={mean_b:.1f}%) → t = {t_stat:.2f}, df ≈ {df_welch:.1f}"
            )
            if abs(t_stat) >= 2:
                st.success(
                    "✅ |t| ≥ 2 (tương đương mức ý nghĩa ~95% khi df đủ lớn) → chênh lệch tỷ lệ đạt quota giữa 2 nhóm "
                    "đủ rõ để ủng hộ nhận định top performer vượt trội."
                )
            else:
                st.warning(
                    "⚠️ |t| < 2 → chênh lệch quan sát được chưa đủ mạnh để kết luận chắc chắn; "
                    "nên theo dõi thêm nhiều kỳ để kiểm định chặt chẽ hơn."
                )
            st.caption("*Lưu ý: đây là kiểm định tham khảo nhanh, độ tin cậy phụ thuộc vào cỡ mẫu (số nhân viên) hiện có.*")
        else:
            st.info("Không đủ dữ liệu ở một trong hai nhóm để chạy kiểm định thống kê.")

        st.divider()

        # ---------- Phần C: Tương quan Thâm niên (SCD2) và Doanh thu ----------
        st.subheader("C. Tương quan giữa Thâm niên và Doanh thu")
        st.caption(
            "Thâm niên được ước lượng bằng số ngày từ phiên bản `dim_seller` đầu tiên (SCD2) "
            "đến ngày kết thúc kỳ đã chọn — đây là giá trị xấp xỉ, không phải ngày vào công ty thực tế."
        )

        q_tenure = """
            SELECT seller_id, MIN(effective_date) AS first_effective_date
            FROM dim_seller
            WHERE seller_id <> -1
            GROUP BY seller_id
        """
        df_tenure = run_query(q_tenure)

        if not df_tenure.empty:
            df_tenure["first_effective_date"] = pd.to_datetime(df_tenure["first_effective_date"])
            df_tenure["tenure_days"] = (pd.Timestamp(end_date) - df_tenure["first_effective_date"]).dt.days

            df_corr = df_sellers.merge(df_tenure[["seller_id", "tenure_days"]], on="seller_id", how="left")
            df_corr = df_corr.dropna(subset=["tenure_days", "total_revenue"])

            if len(df_corr) >= 3:
                corr_value = df_corr["tenure_days"].corr(df_corr["total_revenue"])
                st.metric("Hệ số tương quan Pearson (Thâm niên vs Doanh thu)", f"{corr_value:.2f}")

                fig_corr = px.scatter(
                    df_corr, x="tenure_days", y="total_revenue", hover_name="seller_name",
                    title="Thâm niên (số ngày) vs Doanh thu",
                    labels={"tenure_days": "Thâm niên (ngày)", "total_revenue": "Doanh thu"},
                )
                z = np.polyfit(df_corr["tenure_days"], df_corr["total_revenue"], 1)
                x_line = np.linspace(df_corr["tenure_days"].min(), df_corr["tenure_days"].max(), 50)
                fig_corr.add_scatter(x=x_line, y=z[0] * x_line + z[1], mode="lines", name="Xu hướng (OLS)")
                st.plotly_chart(fig_corr, use_container_width=True)

                if corr_value >= 0.3:
                    st.success(
                        f"✅ Tương quan dương ({corr_value:.2f}) giữa thâm niên và doanh thu "
                        "→ có cơ sở ủng hộ nhận định nhân viên lâu năm nắm giữ nhiều hợp đồng giá trị cao hơn."
                    )
                else:
                    st.warning(
                        f"⚠️ Tương quan quan sát được yếu ({corr_value:.2f}) "
                        "→ chưa đủ bằng chứng cho thấy thâm niên là yếu tố quyết định chính; cần xem xét thêm yếu tố khác "
                        "(ví dụ: số lượng khách hàng quản lý, ngành hàng phụ trách...)."
                    )
                st.caption("*Lưu ý: tương quan không đồng nghĩa với quan hệ nhân quả.*")
            else:
                st.info("Không đủ dữ liệu thâm niên để tính tương quan.")
        else:
            st.info("Không lấy được dữ liệu thâm niên từ `dim_seller`.")
       # ---------- Phần D: Tập trung "tài sản khách hàng" (kiểm định đề xuất CRM) ----------
        st.subheader("D. Mức độ tập trung khách hàng theo nhân viên (kiểm định đề xuất CRM)")
        st.caption(
            "Nếu lượt khách hàng giao dịch cũng tập trung vào cùng một nhóm nhân viên đang dẫn đầu doanh thu, "
            "nghĩa là quan hệ khách hàng đang phụ thuộc vào cá nhân — cần CRM tập trung để công ty không mất "
            "đầu mối khách hàng khi nhân viên đó nghỉ việc."
        )
 
        df_cust_sorted = df_sellers.sort_values("total_customer_visits", ascending=False).reset_index(drop=True)
        total_cust = df_cust_sorted["total_customer_visits"].sum()
 
        def cust_share_top_n(n):
            n = min(n, len(df_cust_sorted))
            return df_cust_sorted["total_customer_visits"].head(n).sum() / total_cust * 100 if total_cust else 0
 
        cust_top20_n = max(1, round(len(df_cust_sorted) * 0.2))
        cust_cr3 = cust_share_top_n(3)
        cust_cr_top20 = cust_share_top_n(cust_top20_n)
        cust_gini = gini_coefficient(df_cust_sorted["total_customer_visits"])
 
        c1, c2, c3 = st.columns(3)
        c1.metric("Top 3 NV / Tổng lượt KH", fmt_pct(cust_cr3))
        c2.metric(f"Top 20% NV ({cust_top20_n} người) / Tổng lượt KH", fmt_pct(cust_cr_top20))
        c3.metric("Gini (lượt khách hàng)", f"{cust_gini:.2f}" if cust_gini is not None else "N/A")
 
        # Độ chồng lấp giữa nhóm Top doanh thu (Phần B) và nhóm Top khách hàng
        top_cust_ids = df_cust_sorted.head(n_top)["seller_id"]
        overlap_ids = set(top_ids.values) & set(top_cust_ids.values)
        overlap_pct = len(overlap_ids) / n_top * 100 if n_top else 0
 
        st.metric(f"Độ chồng lấp: Top {top_pct}% doanh thu ∩ Top {top_pct}% khách hàng", f"{overlap_pct:.0f}%")
 
        if overlap_pct >= 60:
            st.success(
                f"✅ {overlap_pct:.0f}% nhân viên top doanh thu cũng đồng thời là nhân viên nắm nhiều khách hàng nhất "
                "→ cùng một nhóm người vừa tạo ra doanh thu vừa 'sở hữu' quan hệ khách hàng. Đây là bằng chứng ủng hộ "
                "đề xuất CRM tập trung: nếu nhóm này rời đi, công ty có nguy cơ mất cả doanh thu lẫn đầu mối khách hàng."
            )
        else:
            st.warning(
                f"⚠️ Độ chồng lấp chỉ {overlap_pct:.0f}% → quan hệ khách hàng và doanh thu chưa tập trung rõ vào cùng "
                "một nhóm người như giả định; nếu có bảng khách hàng chi tiết (`dim_customer`/`fact_sales`), nên kiểm "
                "định thêm ở mức khách hàng để kết luận chắc chắn hơn."
            )
 
        corr_cust_rev = df_sellers["total_customer_visits"].corr(df_sellers["total_revenue"])
        st.caption(f"Tương quan Pearson giữa số lượt khách hàng và doanh thu: **{corr_cust_rev:.2f}**")
 
        st.divider()
 
        # ---------- Phần E: Cơ chế hoa hồng có phân hoá theo hiệu suất? (kiểm định đề xuất tái thiết kế KPI) ----------
        st.subheader("E. Cơ chế hoa hồng hiện tại có phân hoá theo hiệu suất không? (kiểm định đề xuất tái thiết kế KPI)")
        st.caption(
            "Nếu % hoa hồng gần như đồng nhất giữa các nhân viên bất kể hiệu suất khác nhau, cơ chế hiện tại "
            "chưa tạo động lực phát triển khách hàng mới hay phân bổ lại cơ hội bán hàng — ủng hộ đề xuất tái thiết kế KPI/hoa hồng."
        )
 
        commission_mean = df_sellers["commission_pct"].mean()
        commission_std = df_sellers["commission_pct"].std()
        commission_cv = (commission_std / commission_mean * 100) if commission_mean else None
        corr_comm_perf = df_sellers["commission_pct"].corr(df_sellers["quota_attainment_pct"])
 
        c1, c2, c3 = st.columns(3)
        c1.metric("Hệ số biến thiên (CV) % hoa hồng", f"{commission_cv:.1f}%" if commission_cv is not None else "N/A")
        c2.metric("Tương quan % hoa hồng vs % đạt quota", f"{corr_comm_perf:.2f}" if pd.notna(corr_comm_perf) else "N/A")
        c3.metric("Số mức hoa hồng khác nhau đang áp dụng", df_sellers["commission_pct"].nunique())
 
        if commission_cv is not None and commission_cv < 15 and (pd.isna(corr_comm_perf) or abs(corr_comm_perf) < 0.3):
            st.success(
                "✅ % hoa hồng gần như đồng nhất giữa các nhân viên (CV thấp) và không tương quan rõ với % đạt quota "
                "→ ủng hộ nhận định cơ chế hoa hồng hiện tại chưa gắn với hiệu suất/hành vi mong muốn (phát triển KH mới, "
                "phân bổ lại cơ hội) và cần được tái thiết kế."
            )
        else:
            st.warning(
                "⚠️ % hoa hồng đã có sự phân hoá hoặc tương quan nhất định với hiệu suất "
                "→ nên xem thêm cơ chế thưởng/bonus cụ thể theo khách hàng mới trước khi kết luận cần tái thiết kế toàn bộ."
            )
 
        fig_comm_perf = px.scatter(
            df_sellers, x="commission_pct", y="quota_attainment_pct", hover_name="seller_name",
            title="% Hoa hồng vs % Đạt quota — cơ chế hiện tại có phân hoá theo hiệu suất không?",
            labels={"commission_pct": "% Hoa hồng", "quota_attainment_pct": "% Đạt quota"},
        )
        fig_comm_perf.add_hline(y=100, line_dash="dash", line_color="gray")
        st.plotly_chart(fig_comm_perf, use_container_width=True)
 
        st.caption(
            "*Lưu ý: kiểm định D & E dùng dữ liệu tổng hợp hiện có (`total_customer_visits`, `commission_pct`). "
            "Nếu hệ thống có bảng khách hàng chi tiết theo từng nhân viên (VD: `dim_customer`, `fact_sales`), nên bổ sung "
            "kiểm định tỷ lệ khách hàng chỉ giao dịch qua đúng 1 nhân viên để đánh giá rủi ro CRM chính xác hơn.*"
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