# Gold DW Analytics Dashboard

App Streamlit đa trang phân tích dữ liệu tầng Gold (Star Schema, PostgreSQL `gold_dw`) dựa trên `init.sql` đã cung cấp.

## Cấu trúc dự án

```
dw_dashboard/
├── Home.py                              # Trang chủ: KPI tổng quan + điều hướng
├── utils/
│   ├── db.py                            # Kết nối DB, run_query (cache 10 phút), helpers format số
│   └── helpers.py                       # Gộp nhóm theo granularity (ngày/tuần/tháng/quý/năm), tính growth %
├── pages/
│   ├── 1_Doanh_thu_Don_hang.py          # fact_order · fact_order_daily
│   ├── 2_Hieu_suat_San_pham.py          # fact_product_daily · dim_product (SCD2)
│   ├── 3_Hanh_vi_Khach_hang.py          # fact_customer_behavior · dim_customer (SCD2)
│   └── 4_Hieu_suat_Nhan_vien.py         # fact_seller_daily · dim_seller (SCD2)
└── requirements.txt
```

## Chạy thử

```bash
pip install -r requirements.txt

# Biến môi trường (mặc định khớp với init.sql / Docker Compose của bạn)
export POSTGRES_HOST=localhost   # hoặc postgres-gold nếu chạy trong cùng Docker network
export POSTGRES_USER=gold_user
export POSTGRES_PASSWORD=adminpassword
export POSTGRES_DB=gold_dw

streamlit run Home.py
```

## Nội dung từng trang

**1. Doanh thu & Đơn hàng** — 4 tab: xu hướng doanh thu/AOV theo granularity tuỳ chọn, so sánh kênh Online/Offline, phân tích chiết khấu/thuế/phí vận chuyển, tăng trưởng so với kỳ trước.

**2. Hiệu suất Sản phẩm** — Top/Bottom sản phẩm, treemap danh mục, biên lợi nhuận gộp, snapshot giá vốn/giá niêm yết theo ngày, tác động đổi giá đến doanh số (dựa trên các phiên bản SCD2 của `dim_product`).

**3. Hành vi Khách hàng** — RFM (ngũ phân vị + phân khúc), Customer Lifetime Value ước tính, Cohort Retention theo tháng mua đầu tiên, khoảng cách giữa các lần mua hàng.

**4. Hiệu suất Nhân viên bán** — Leaderboard doanh thu/hoa hồng, tỷ lệ đạt quota (có tuỳ chọn quy đổi quota theo số ngày), lịch sử thay đổi quota/bonus (SCD2).

Mỗi trang có khung **🧠 Gợi ý SQL** ở cuối để xem lại truy vấn đã dùng — kèm lưu ý quan trọng về việc tránh đếm trùng (`sub_total`, `tax_amt`, `freight_amt`, `total_due` là field cấp header bị lặp trên line-item trong `fact_order`, nên phải `DISTINCT` theo `order_id` trước khi `SUM`).

## Ghi chú thiết kế

- Mọi truy vấn dùng tham số có tên (`:start_date`, …) qua SQLAlchemy `text()`, tránh SQL injection.
- `@st.cache_data(ttl=600)` áp dụng cho `run_query` — bấm **"🔄 Làm mới dữ liệu"** ở sidebar để xoá cache khi cần dữ liệu mới nhất.
- Với `dim_product`, `dim_customer`, `dim_seller` (SCD2): các phân tích tổng hợp theo thời gian nhóm theo `*_id` (business key) thay vì `*_key` (surrogate key đổi theo từng phiên bản), trong khi các phân tích "snapshot tại thời điểm" (giá, quota...) dùng đúng `*_key`/`version` để phản ánh đúng giá trị tại từng thời điểm.
