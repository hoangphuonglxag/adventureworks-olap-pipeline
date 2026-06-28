# =============================================================================
# gold_builders.py
# Advanced Star Schema Transformation Logic (Silver --> Gold)
# AdventureWorks2022
#
# NOTE: Đọc từ Silver schema thực tế (mixed case) — xuất ra Gold với snake_case chuẩn
# =============================================================================

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# =============================================================================
# 1. DIMENSIONS BUILDERS
# =============================================================================

def build_dim_customer(silver_customer: DataFrame) -> DataFrame:
    """
    Grain: 1 dòng = 1 Khách hàng duy nhất.
    Silver customer columns (thực tế): customer_id, customer_name, customer_type, account_number
    """
    return silver_customer.select(
        F.sha2(F.col("customer_id").cast("string"), 256).alias("customer_key"),
        F.col("customer_id"),
        F.col("customer_type"),
        F.col("customer_name").alias("full_name"),   # Silver lưu customer_name
        F.lit("Unknown").alias("email"),
        F.lit("Unknown").alias("phone")
    )


def build_dim_product(silver_product: DataFrame) -> DataFrame:
    """
    Grain: 1 dòng = 1 Sản phẩm duy nhất.
    Silver product columns (thực tế): product_id, product_name, ProductNumber,
                                      Color, Size, StandardCost, ListPrice,
                                      category_name, subcategory_name
    """
    return silver_product.select(
        F.sha2(F.col("product_id").cast("string"), 256).alias("product_key"),
        F.col("product_id"),
        F.col("product_name"),
        F.col("ProductNumber").alias("product_number"),
        F.col("Color").alias("color"),
        F.col("Size").alias("size"),
        F.col("StandardCost").alias("standard_cost"),
        F.col("ListPrice").alias("list_price"),
        F.col("category_name"),
        F.col("subcategory_name"),
        F.lit("B").alias("abc_class")
    )


def build_dim_geography(silver_geography: DataFrame) -> DataFrame:
    """
    Grain: 1 dòng = 1 Địa chỉ duy nhất.
    Silver geography columns (thực tế): address_id, AddressLine1, AddressLine2,
                                         City, state_name, country_name,
                                         territory_name, territory_group, PostalCode
    """
    return silver_geography.select(
        F.sha2(F.col("address_id").cast("string"), 256).alias("geography_key"),
        F.col("address_id"),
        F.col("City").alias("city"),
        F.col("state_name").alias("state_province_name"),
        F.col("country_name").alias("country_region_name"),
        F.col("territory_name"),
        F.col("territory_group")
    )


def build_dim_seller(silver_seller: DataFrame) -> DataFrame:
    """
    Grain: 1 dòng = 1 Nhân viên sales.
    Silver seller columns (thực tế): seller_id, full_name, SalesQuota,
                                      Bonus, CommissionPct, SalesYTD, SalesLastYear
    """
    return silver_seller.select(
        F.sha2(F.col("seller_id").cast("string"), 256).alias("seller_key"),
        F.col("seller_id").alias("business_entity_id"),
        F.col("full_name"),
        F.col("CommissionPct").alias("commission_pct"),
        F.col("SalesQuota").alias("sales_quota"),
        F.col("Bonus").alias("bonus")
    )


def build_dim_date(spark: SparkSession) -> DataFrame:
    """Tạo bảng Dim_Date tự động từ năm 2010 đến 2030"""
    df = spark.sql(
        "SELECT explode(sequence(to_date('2010-01-01'), to_date('2030-12-31'), interval 1 day)) as full_date"
    )
    return df.select(
        F.date_format(F.col("full_date"), "yyyyMMdd").cast("int").alias("date_key"),
        F.col("full_date"),
        F.date_format(F.col("full_date"), "EEEE").alias("day_name"),
        F.dayofweek(F.col("full_date")).alias("day_of_week"),   # 1=Sun, 2=Mon, ..., 7=Sat
        F.month(F.col("full_date")).alias("month_num"),
        F.date_format(F.col("full_date"), "MMMM").alias("month_name"),
        F.quarter(F.col("full_date")).alias("quarter"),
        F.year(F.col("full_date")).alias("year"),
        F.when(F.dayofweek(F.col("full_date")).isin(1, 7), True)
         .otherwise(False).alias("is_weekend")
    )


# =============================================================================
# 2. FACTS BUILDERS
# =============================================================================

def build_fact_order(
    silver_header: DataFrame,
    dim_customer: DataFrame,
    dim_seller: DataFrame
) -> DataFrame:
    """
    Grain: 1 dòng = 1 Đơn hàng duy nhất.
    Silver header columns (thực tế): order_id, customer_id, sales_person_id,
        TerritoryID, OrderDate, DueDate, ShipDate, Status, sales_channel,
        SubTotal, TaxAmt, Freight, TotalDue
    """
    df_mapped = (
        silver_header.alias("h")
        .join(
            dim_customer.select("customer_id", "customer_key").alias("c"),
            F.col("h.customer_id") == F.col("c.customer_id"),
            "left"
        )
        .join(
            dim_seller.select(
                F.col("business_entity_id").alias("seller_biz_id"),
                "seller_key"
            ).alias("s"),
            F.col("h.sales_person_id") == F.col("s.seller_biz_id"),
            "left"
        )
    )

    return df_mapped.select(
        F.sha2(F.col("h.order_id").cast("string"), 256).alias("order_fact_key"),
        F.col("h.order_id"),
        F.date_format(F.col("h.OrderDate"), "yyyyMMdd").cast("int").alias("date_key"),
        F.coalesce(F.col("c.customer_key"), F.lit(-1)).alias("customer_key"),
        F.coalesce(F.col("s.seller_key"), F.lit(-1)).alias("seller_key"),
        F.col("h.TerritoryID").alias("territory_id"),
        F.col("h.sales_channel"),
        F.col("h.TotalDue").alias("total_due"),
        F.col("h.TaxAmt").alias("tax_amt"),
        F.col("h.Freight").alias("freight_amt"),
        F.col("h.Status").alias("order_status")
    )


def build_fact_product_daily(
    silver_header: DataFrame,
    silver_detail: DataFrame,
    dim_product: DataFrame
) -> DataFrame:
    """
    Grain: 1 dòng = 1 sản phẩm / 1 ngày / 1 territory / 1 kênh bán.
    Silver detail columns (thực tế): order_id, order_detail_id, product_id,
        OrderQty, UnitPrice, UnitPriceDiscount, LineTotal
    Silver header columns (thực tế): order_id, OrderDate, TerritoryID, sales_channel
    """
    df_join = (
        silver_detail.alias("d")
        .join(
            silver_header.select(
                "order_id", "OrderDate", "TerritoryID", "sales_channel"
            ).alias("h"),
            F.col("d.order_id") == F.col("h.order_id"),
            "inner"
        )
    )

    df_grouped = df_join.groupBy(
        F.col("h.OrderDate"),
        F.col("d.product_id"),
        F.col("h.TerritoryID"),
        F.col("h.sales_channel")
    ).agg(
        F.sum("d.OrderQty").alias("quantity_sold"),
        F.countDistinct("d.order_id").alias("total_orders"),
        F.sum("d.LineTotal").alias("revenue"),
        F.avg("d.UnitPrice").alias("avg_price"),
        F.lit(0).alias("return_qty"),
        F.lit(0.0).alias("return_rate")
    )

    df_final = (
        df_grouped.alias("f")
        .join(
            dim_product.select("product_id", "product_key", "standard_cost").alias("p"),
            F.col("f.product_id") == F.col("p.product_id"),
            "left"
        )
    )

    return df_final.select(
        F.sha2(
            F.concat_ws("||", F.col("f.OrderDate"), F.col("f.product_id"),
                        F.col("f.TerritoryID"), F.col("f.sales_channel")),
            256
        ).alias("product_fact_key"),
        F.date_format(F.col("f.OrderDate"), "yyyyMMdd").cast("int").alias("date_key"),
        F.coalesce(F.col("p.product_key"), F.lit(-1)).alias("product_key"),
        F.col("f.TerritoryID").alias("territory_id"),
        F.col("f.sales_channel"),
        F.col("quantity_sold").cast("int"),
        F.col("total_orders").cast("int"),
        F.col("revenue").cast("decimal(18,4)"),
        F.when(
            F.col("p.standard_cost").isNotNull(),
            (F.col("revenue") - (F.col("quantity_sold") * F.col("p.standard_cost")))
        ).otherwise(F.col("revenue")).cast("decimal(18,4)").alias("gross_profit"),
        F.col("avg_price").cast("decimal(18,4)"),
        F.col("return_qty").cast("int"),
        F.col("return_rate").cast("decimal(5,4)")
    )


def build_fact_order_daily(fact_product_daily: DataFrame) -> DataFrame:
    """Grain: 1 dòng = 1 ngày / 1 territory / 1 kênh bán"""
    df_grouped = fact_product_daily.groupBy(
        F.col("date_key"),
        F.col("territory_id"),
        F.col("sales_channel")
    ).agg(
        F.sum("revenue").alias("daily_revenue"),
        F.sum("gross_profit").alias("daily_profit"),
        F.sum("total_orders").alias("daily_order_count")
    )

    return df_grouped.select(
        F.sha2(
            F.concat_ws("||", F.col("date_key"), F.col("territory_id"), F.col("sales_channel")),
            256
        ).alias("order_daily_key"),
        "date_key",
        "territory_id",
        "sales_channel",
        "daily_revenue",
        "daily_profit",
        "daily_order_count"
    )