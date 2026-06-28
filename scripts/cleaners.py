# =============================================================================
# cleaners.py
# Generic Data Cleaning Functions for Silver Layer
# AdventureWorks2022
# =============================================================================

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StringType,
    DecimalType,
    DoubleType,
    FloatType,
    IntegerType,
    LongType,
    TimestampType,
    DateType
)


# =============================================================================
# STRING CLEANING
# =============================================================================

def trim_string_columns(df: DataFrame) -> DataFrame:
    """
    Trim khoảng trắng của tất cả cột String
    """

    for field in df.schema.fields:
        if isinstance(field.dataType, StringType):
            df = df.withColumn(
                field.name,
                F.trim(F.col(field.name))
            )

    return df


def empty_to_null(df: DataFrame) -> DataFrame:
    """
    Chuyển '' thành NULL
    """

    for field in df.schema.fields:
        if isinstance(field.dataType, StringType):
            df = df.withColumn(
                field.name,
                F.when(
                    F.length(F.trim(F.col(field.name))) == 0,
                    None
                ).otherwise(F.col(field.name))
            )

    return df


# =============================================================================
# EMAIL
# =============================================================================

def normalize_email(df: DataFrame) -> DataFrame:
    """
    Email -> lowercase
    """

    for col in df.columns:

        if "email" in col.lower():

            df = df.withColumn(
                col,
                F.lower(F.col(col))
            )

    return df


# =============================================================================
# PHONE
# =============================================================================

def normalize_phone(df: DataFrame) -> DataFrame:
    """
    Xóa ký tự đặc biệt khỏi số điện thoại
    """

    for col in df.columns:

        if "phone" in col.lower():

            df = df.withColumn(
                col,
                F.regexp_replace(
                    F.col(col),
                    "[^0-9]",
                    ""
                )
            )

    return df


# =============================================================================
# DUPLICATE
# =============================================================================

def remove_duplicates(
    df: DataFrame,
    primary_key: list
) -> DataFrame:
    """
    Remove duplicate theo Primary Key
    """

    return df.dropDuplicates(primary_key)


# =============================================================================
# PRIMARY KEY
# =============================================================================

def validate_primary_key(
    df: DataFrame,
    primary_key: list
) -> DataFrame:
    """
    Loại bỏ record có PK NULL
    """

    condition = None

    for col in primary_key:

        if condition is None:
            condition = F.col(col).isNotNull()
        else:
            condition = condition & F.col(col).isNotNull()

    return df.filter(condition)


# =============================================================================
# DECIMAL
# =============================================================================

def cast_decimal(
    df: DataFrame,
    columns: list,
    precision: int = 18,
    scale: int = 4
) -> DataFrame:
    """
    Cast các cột Decimal
    """

    for col in columns:

        if col in df.columns:

            df = df.withColumn(
                col,
                F.col(col).cast(
                    DecimalType(precision, scale)
                )
            )

    return df


# =============================================================================
# INTEGER
# =============================================================================

def cast_integer(
    df: DataFrame,
    columns: list
) -> DataFrame:

    for col in columns:

        if col in df.columns:

            df = df.withColumn(
                col,
                F.col(col).cast(IntegerType())
            )

    return df


# =============================================================================
# DATE
# =============================================================================

def cast_date(
    df: DataFrame,
    columns: list
) -> DataFrame:

    for col in columns:

        if col in df.columns:

            df = df.withColumn(
                col,
                F.to_date(F.col(col))
            )

    return df


# =============================================================================
# TIMESTAMP
# =============================================================================

def cast_timestamp(
    df: DataFrame,
    columns: list
) -> DataFrame:

    for col in columns:

        if col in df.columns:

            df = df.withColumn(
                col,
                F.to_timestamp(F.col(col))
            )

    return df


# =============================================================================
# POSITIVE NUMBER
# =============================================================================

def validate_positive(
    df: DataFrame,
    columns: list
) -> DataFrame:
    """
    Chỉ giữ giá trị >=0
    """

    for col in columns:

        if col in df.columns:

            df = df.filter(
                (F.col(col).isNull()) |
                (F.col(col) >= 0)
            )

    return df


# =============================================================================
# DEFAULT VALUE
# =============================================================================

def fill_string(
    df: DataFrame,
    column: str,
    value: str
) -> DataFrame:

    if column in df.columns:

        df = df.withColumn(
            column,
            F.coalesce(
                F.col(column),
                F.lit(value)
            )
        )

    return df


def fill_numeric(
    df: DataFrame,
    column: str,
    value
) -> DataFrame:

    if column in df.columns:

        df = df.withColumn(
            column,
            F.coalesce(
                F.col(column),
                F.lit(value)
            )
        )

    return df


# =============================================================================
# TITLE CASE
# =============================================================================

def title_case(
    df: DataFrame,
    columns: list
) -> DataFrame:

    for col in columns:

        if col in df.columns:

            df = df.withColumn(
                col,
                F.initcap(F.col(col))
            )

    return df


# =============================================================================
# AUDIT
# =============================================================================

def add_audit_columns(df: DataFrame) -> DataFrame:
    """
    Thêm metadata cho Silver
    """

    return (
        df
        .withColumn(
            "_processed_at",
            F.current_timestamp()
        )
        .withColumn(
            "_layer",
            F.lit("silver")
        )
    )


# =============================================================================
# GENERIC CLEAN
# =============================================================================

def generic_clean(
    df: DataFrame,
    primary_key: list = None
) -> DataFrame:
    """
    Generic Cleaning dùng cho mọi bảng
    """

    df = trim_string_columns(df)

    df = empty_to_null(df)

    df = normalize_email(df)

    df = normalize_phone(df)

    if primary_key:

        df = validate_primary_key(
            df,
            primary_key
        )

        df = remove_duplicates(
            df,
            primary_key
        )

    df = add_audit_columns(df)

    return df