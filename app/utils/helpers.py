"""
helpers.py — Hàm tiện ích dùng chung cho các trang phân tích.
"""
import pandas as pd

GRANULARITY_OPTIONS = ["Ngày", "Tuần", "Tháng", "Quý", "Năm"]


def add_period_column(df: pd.DataFrame, date_col: str, granularity: str) -> pd.DataFrame:
    """
    Thêm cột 'period' (mốc thời gian dùng để sort/group, kiểu datetime)
    và 'period_label' (chuỗi hiển thị trên biểu đồ) theo granularity đã chọn.
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])

    if granularity == "Ngày":
        df["period"] = df[date_col].dt.normalize()
        df["period_label"] = df["period"].dt.strftime("%d/%m/%Y")
    elif granularity == "Tuần":
        iso = df[date_col].dt.isocalendar()
        df["period"] = df[date_col].dt.to_period("W").dt.start_time
        df["period_label"] = "Tuần " + iso["week"].astype(str) + "/" + iso["year"].astype(str)
    elif granularity == "Tháng":
        df["period"] = df[date_col].values.astype("datetime64[M]")
        df["period_label"] = df[date_col].dt.strftime("%m/%Y")
    elif granularity == "Quý":
        df["period"] = df[date_col].dt.to_period("Q").dt.start_time
        df["period_label"] = "Q" + df[date_col].dt.quarter.astype(str) + "/" + df[date_col].dt.year.astype(str)
    else:  # Năm
        df["period"] = df[date_col].values.astype("datetime64[Y]")
        df["period_label"] = df[date_col].dt.strftime("%Y")

    return df


def growth_pct(current: float, previous: float):
    """% thay đổi so với kỳ trước. Trả về None nếu không tính được."""
    if previous in (0, None) or pd.isna(previous):
        return None
    return (current - previous) / previous * 100


def normalize_date_range(date_input_value, fallback_min, fallback_max):
    """
    st.date_input với range trả về tuple (start, end), nhưng khi người dùng
    mới chọn 1 ngày thì trả về 1 ngày đơn lẻ → hàm này chuẩn hoá lại thành (start, end).
    """
    if isinstance(date_input_value, (tuple, list)):
        if len(date_input_value) == 2:
            return date_input_value[0], date_input_value[1]
        if len(date_input_value) == 1:
            return date_input_value[0], date_input_value[0]
    return fallback_min, fallback_max
