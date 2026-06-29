# =============================================================================
# business_cleaners.py
# Business Cleaning Logic - AdventureWorks2022
# =============================================================================

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from cleaners import (
    generic_clean,
    cast_decimal,
    cast_date,
    fill_string,
    validate_positive,
    title_case
)

# =============================================================================
# CUSTOMER đã xong 
# =============================================================================

def clean_customer(
    customer_df: DataFrame,
    person_df: DataFrame,
    store_df: DataFrame
) -> DataFrame:

    customer_df = generic_clean(customer_df, ["CustomerID"])
    person_df = generic_clean(person_df, ["BusinessEntityID"])
    store_df = generic_clean(store_df, ["BusinessEntityID"])

    person_df = person_df.withColumn(
        "full_name",
        F.concat_ws(
            " ",
            F.col("FirstName"),
            F.col("MiddleName"),
            F.col("LastName")
        )
    )

    df = (
        customer_df.alias("c")
        .join(
            person_df.alias("p"),
            F.col("c.PersonID") == F.col("p.BusinessEntityID"),
            "left"
        )
        .join(
            store_df.alias("s"),
            F.col("c.StoreID") == F.col("s.BusinessEntityID"),
            "left"
        )
    )

    df = df.withColumn(
        "customer_name",
        F.coalesce(
            F.col("p.full_name"),
            F.col("s.Name")
        )
    )

    df = df.withColumn(
        "customer_type",
        F.when(
            F.col("c.StoreID").isNotNull(),
            "Store"
        ).otherwise("Individual")
    )

    return df.select(
        F.col("c.CustomerID").alias("customer_id"),
        "customer_name",
        "customer_type",
        F.col("c.AccountNumber").alias("account_number")
    )


# =============================================================================
# PRODUCT
# =============================================================================

def clean_product(
    product_df: DataFrame,
    subcategory_df: DataFrame,
    category_df: DataFrame
) -> DataFrame:

    product_df = generic_clean(product_df, ["ProductID"])
    subcategory_df = generic_clean(subcategory_df, ["ProductSubcategoryID"])
    category_df = generic_clean(category_df, ["ProductCategoryID"])

    product_df = fill_string(product_df, "Color", "Unknown")
    product_df = fill_string(product_df, "Size", "Unknown")

    product_df = cast_decimal(
        product_df,
        ["StandardCost", "ListPrice"]
    )

    product_df = validate_positive(
        product_df,
        ["StandardCost", "ListPrice"]
    )

    product_df = title_case(
        product_df,
        ["Name", "Color"]
    )

    df = (
        product_df.alias("p")
        .join(
            subcategory_df.alias("s"),
            "ProductSubcategoryID",
            "left"
        )
        .join(
            category_df.alias("c"),
            "ProductCategoryID",
            "left"
        )
    )

    return df.select(
        F.col("ProductID").alias("product_id"),
        F.col("p.Name").alias("product_name"),
        "ProductNumber",
        "Color",
        "Size",
        "StandardCost",
        "ListPrice",
        F.col("c.Name").alias("category_name"),
        F.col("s.Name").alias("subcategory_name")
    )


# =============================================================================
# GEOGRAPHY
# =============================================================================

def clean_geography(
    address_df: DataFrame,
    state_df: DataFrame,
    country_df: DataFrame,
    territory_df: DataFrame
) -> DataFrame:

    address_df = generic_clean(address_df, ["AddressID"])
    state_df = generic_clean(state_df, ["StateProvinceID"])
    country_df = generic_clean(country_df, ["CountryRegionCode"])
    territory_df = generic_clean(territory_df, ["TerritoryID"])

    address_df = title_case(
        address_df,
        ["City"]
    )

    df = (
        address_df.alias("a")
        .join(
            state_df.alias("s"),
            "StateProvinceID",
            "left"
        )
        .join(
            country_df.alias("c"),
            "CountryRegionCode",
            "left"
        )
        .join(
            territory_df.alias("t"),
            "TerritoryID",
            "left"
        )
    )

    return df.select(
        F.col("AddressID").alias("address_id"),
        "AddressLine1",
        "AddressLine2",
        "City",
        F.col("s.Name").alias("state_name"),
        F.col("c.Name").alias("country_name"),
        F.col("t.Name").alias("territory_name"),
        F.col("t.Group").alias("territory_group"),
        "PostalCode"
    )


# =============================================================================
# SALES ORDER HEADER
# =============================================================================

def clean_sales_header(
    df: DataFrame
) -> DataFrame:

    df = generic_clean(df, ["SalesOrderID"])

    df = cast_decimal(
        df,
        [
            "SubTotal",
            "TaxAmt",
            "Freight",
            "TotalDue"
        ]
    )

    df = validate_positive(
        df,
        [
            "SubTotal",
            "TaxAmt",
            "Freight",
            "TotalDue"
        ]
    )

    df = cast_date(
        df,
        [
            "OrderDate",
            "DueDate",
            "ShipDate"
        ]
    )

    df = df.withColumn(
        "sales_channel",
        F.when(
            F.col("OnlineOrderFlag"),
            "Online"
        ).otherwise("Offline")
    )

    return df.select(
        F.col("SalesOrderID").alias("order_id"),
        F.col("CustomerID").alias("customer_id"),
        F.col("SalesPersonID").alias("sales_person_id"),
        F.col("TerritoryID").alias("territory_id"),
        F.col("OrderDate").alias("order_date"),
        F.col("DueDate").alias("due_date"),
        F.col("ShipDate").alias("ship_date"),
        F.col("Status").alias("status"),
        "sales_channel",
        F.col("SubTotal").alias("sub_total"),
        F.col("TaxAmt").alias("tax_amt"),
        F.col("Freight").alias("freight_amt"),
        F.col("TotalDue").alias("total_due")
    )


# =============================================================================
# SALES ORDER DETAIL
# =============================================================================

def clean_sales_detail(
    df: DataFrame
) -> DataFrame:

    df = generic_clean(
        df,
        ["SalesOrderDetailID"]
    )

    df = cast_decimal(
        df,
        [
            "UnitPrice",
            "UnitPriceDiscount",
            "LineTotal"
        ]
    )

    df = validate_positive(
        df,
        [
            "OrderQty",
            "UnitPrice",
            "LineTotal"
        ]
    )

    return df.select(
        F.col("SalesOrderID").alias("order_id"),
        F.col("SalesOrderDetailID").alias("order_detail_id"),
        F.col("ProductID").alias("product_id"),
        F.col("OrderQty").alias("order_qty"),
        F.col("UnitPrice").alias("unit_price"),
        F.col("UnitPriceDiscount").alias("unit_price_discount"),
        F.col("LineTotal").alias("line_total")
    )


# =============================================================================
# VENDOR
# =============================================================================

def clean_vendor(
    df: DataFrame
) -> DataFrame:

    df = generic_clean(
        df,
        ["BusinessEntityID"]
    )

    df = title_case(
        df,
        ["Name"]
    )

    return df.select(
        F.col("BusinessEntityID").alias("vendor_id"),
        "AccountNumber",
        "Name",
        "CreditRating",
        "PreferredVendorStatus",
        "ActiveFlag"
    )


# =============================================================================
# SELLER
# =============================================================================

def clean_seller(
    salesperson_df: DataFrame,
    person_df: DataFrame
) -> DataFrame:

    salesperson_df = generic_clean(
        salesperson_df,
        ["BusinessEntityID"]
    )

    person_df = generic_clean(
        person_df,
        ["BusinessEntityID"]
    )

    person_df = person_df.withColumn(
        "full_name",
        F.concat_ws(
            " ",
            "FirstName",
            "MiddleName",
            "LastName"
        )
    )

    df = salesperson_df.join(
        person_df,
        "BusinessEntityID",
        "left"
    )

    return df.select(
        F.col("BusinessEntityID").alias("seller_id"),
        "full_name",
        "SalesQuota",
        "Bonus",
        "CommissionPct",
        "SalesYTD",
        "SalesLastYear"
    )
def clean_inventory(df):

    df = generic_clean(df, ["ProductID", "LocationID"])

    df = validate_positive(
        df,
        ["Quantity"]
    )

    return df.select(
        F.col("ProductID").alias("product_id"),
        F.col("LocationID").alias("location_id"),
        F.col("Shelf").alias("shelf"),
        F.col("Bin").alias("bin"),
        F.col("Quantity").alias("quantity")
    )