# Enterprise Data Warehouse — Multi-Domain OLTP

[![Airflow](https://img.shields.io/badge/Airflow-017CEE?style=flat-square&logo=apacheairflow&logoColor=white)](https://airflow.apache.org/)
[![Spark](https://img.shields.io/badge/Spark-E25A1C?style=flat-square&logo=apachespark&logoColor=white)](https://spark.apache.org/)
[![SQL Server](https://img.shields.io/badge/SQL%20Server-CC2927?style=flat-square&logo=microsoftsqlserver&logoColor=white)](https://www.microsoft.com/sql-server)
[![MinIO](https://img.shields.io/badge/MinIO-C72E49?style=flat-square&logo=minio&logoColor=white)](https://min.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

 Xây dựng hệ thống **Enterprise Data Warehouse** từ cơ sở dữ liệu giao dịch Microsoft AdventureWorks, tập trung vào thiết kế kiến trúc dữ liệu, xây dựng pipeline ETL batch, mô hình hóa Data Warehouse và triển khai các bài toán phân tích dữ liệu.

 Hệ thống tích hợp dữ liệu từ nhiều miền nghiệp vụ như **Sales, Production, Purchasing, Human Resources và Customer**, sau đó xử lý qua kiến trúc **Medallion Architecture** gồm Bronze → Silver → Gold.

---

 ## 1\. Tổng quan

 AdventureWorks là cơ sở dữ liệu OLTP có cấu trúc quan hệ và nhiều bảng liên kết giữa các miền nghiệp vụ.

 Nếu sử dụng trực tiếp OLTP cho mục đích phân tích, hệ thống phải thực hiện nhiều phép JOIN giữa các bảng chuẩn hóa, đồng thời khó quản lý lịch sử thay đổi dữ liệu và khó tái sử dụng các logic xử lý.

 Project này xây dựng một pipeline dữ liệu nhằm chuyển đổi dữ liệu từ:

```
SQL Server OLTP
       │
       ▼
   Bronze Layer
     MinIO
       │
       ▼
   Silver Layer
   Apache Spark
       │
       ▼
    Gold Layer
   PostgreSQL DWH
       │
       ├───────────────┐
       ▼               ▼
  Analytics       Streamlit
                  Dashboard
```

 Mục tiêu chính:

 - Xây dựng pipeline ingestion từ SQL Server.
- Lưu trữ dữ liệu raw tại MinIO dưới dạng Parquet.
- Làm sạch và chuẩn hóa dữ liệu bằng Apache Spark.
- Theo dõi lịch sử thay đổi bằng SCD Type 2.
- Thiết kế Data Warehouse theo Star Schema.
- Xây dựng các dataset phục vụ phân tích kinh doanh.
- Thực hiện Customer Segmentation bằng RFM \+ K-Means.
- Phân loại sản phẩm bằng ABC Analysis.
- Trực quan hóa kết quả thông qua Streamlit.

---

 # 2\. Kiến trúc hệ thống

```
                        ┌───────────────────────┐
                        │     SQL Server OLTP   │
                        │      AdventureWorks   │
                        └───────────┬───────────┘
                                    │
                                    │ JDBC
                                    ▼
                        ┌───────────────────────┐
                        │     Apache Airflow    │
                        │     DAG Orchestration │
                        └───────────┬───────────┘
                                    │
                                    ▼
                 ┌──────────────────────────────────┐
                 │          BRONZE LAYER             │
                 │                                  │
                 │            MinIO / S3            │
                 │                                  │
                 │        Raw Data - Parquet        │
                 └────────────────┬─────────────────┘
                                  │
                                  │ Apache Spark
                                  ▼
                 ┌──────────────────────────────────┐
                 │           SILVER LAYER           │
                 │                                  │
                 │      Cleansing & Processing      │
                 │                                  │
                 │  • Data Cleaning                 │
                 │  • Deduplication                 │
                 │  • Data Validation               │
                 │  • SCD Type 2                    │
                 │  • Referential Integrity         │
                 └────────────────┬─────────────────┘
                                  │
                                  │ Apache Spark
                                  ▼
                 ┌──────────────────────────────────┐
                 │            GOLD LAYER             │
                 │                                  │
                 │       PostgreSQL Data Warehouse   │
                 │                                  │
                 │          Star Schema              │
                 │                                  │
                 │   Fact Tables + Dimension Tables │
                 └────────────────┬─────────────────┘
                                  │
                     ┌────────────┴────────────┐
                     │                         │
                     ▼                         ▼
              ┌───────────────┐        ┌────────────────┐
              │   Analytics   │        │    Streamlit   │
              │               │        │    Dashboard   │
              │ RFM / K-Means │        │                │
              │ ABC Analysis  │        │ Sales          │
              │ Retention     │        │ Customer       │
              │ Inventory     │        │ Product        │
              │ Sales         │        │ Employee       │
              └───────────────┘        └────────────────┘
```

---

 # 3\. Công nghệ sử dụng

 | Thành phần | Công nghệ |
| --- | --- |
| Source OLTP | Microsoft SQL Server |
| Orchestration | Apache Airflow |
| Distributed Processing | Apache Spark |
| Object Storage | MinIO |
| Storage Format | Apache Parquet |
| Data Warehouse | PostgreSQL |
| Data Modeling | Star Schema |
| Historical Tracking | SCD Type 2 |
| Advanced Analytics | Spark MLlib |
| Machine Learning | K-Means |
| Customer Analytics | RFM Analysis |
| Product Analytics | ABC Analysis |
| Dashboard | Streamlit |
| Containerization | Docker |
| Programming | Python, SQL |

---

 # 4\. Nguồn dữ liệu

 Nguồn dữ liệu chính là **Microsoft AdventureWorks OLTP** với khoảng **26 bảng được sử dụng** từ nhiều miền nghiệp vụ.

 ### Các domain chính

```
Sales
 │
 ├── Sales Order
 ├── Customer
 ├── Sales Person
 └── Territory

Production
 │
 ├── Product
 ├── Product Category
 └── Product Subcategory

Purchasing
 │
 ├── Vendor
 └── Purchase Order

Human Resources
 │
 ├── Employee
 └── Department

Person
 │
 ├── Person
 ├── Address
 └── Contact Information
```

 Dữ liệu được lấy từ OLTP và đưa vào hệ thống Data Warehouse thông qua pipeline batch.

---

 # 5\. Medallion Architecture

 ## Bronze Layer

 Bronze là tầng lưu trữ dữ liệu thô được lấy trực tiếp từ SQL Server.

```
SQL Server
     │
     │ JDBC
     ▼
Airflow DAG
     │
     ▼
MinIO
     │
     └── Bronze
          ├── Sales
          ├── Production
          ├── Purchasing
          ├── HumanResources
          └── Person
```

 Dữ liệu được lưu dưới dạng **Parquet** nhằm:

 - Giữ lại dữ liệu raw.
- Tách hệ thống analytical khỏi OLTP.
- Hỗ trợ xử lý hiệu quả bằng Spark.
- Cho phép pipeline có thể xử lý lại dữ liệu từ đầu.

---

 # 6\. Silver Layer

 Silver layer chịu trách nhiệm xử lý và chuẩn hóa dữ liệu từ Bronze.

 Các bước chính:

 - Chuẩn hóa schema.
- Chuẩn hóa data type.
- Xử lý NULL.
- Loại bỏ duplicate.
- Chuẩn hóa text.
- Kiểm tra dữ liệu không hợp lệ.
- Kiểm tra Referential Integrity.
- Xử lý lịch sử thay đổi bằng SCD Type 2.

 Pipeline được thực hiện chủ yếu bằng **Apache Spark**.

```
Bronze
   │
   ▼
Read Parquet
   │
   ▼
Data Cleaning
   │
   ▼
Data Validation
   │
   ▼
SCD Type 2
   │
   ▼
Silver Dataset
```

---

 # 7\. SCD Type 2

 Đối với các dimension cần theo dõi lịch sử, hệ thống sử dụng **Slowly Changing Dimension Type 2**.

 Ví dụ khi địa chỉ của khách hàng thay đổi:

```
customer_id | address   | start_date | end_date   | is_current
------------|-----------|------------|------------|-----------
1001        | Address A | 2012-01-01 | 2013-06-15 | false
1001        | Address B | 2013-06-16 | NULL       | true
```

 Các trường quản lý lịch sử:

```
start_date
end_date
is_current
```

 Nhờ đó có thể truy vấn trạng thái của dimension tại từng thời điểm thay vì chỉ giữ lại giá trị mới nhất.

---

 # 8\. Gold Layer — Data Warehouse

 Gold layer là tầng phục vụ phân tích và được lưu trên **PostgreSQL**.

 Data Warehouse được thiết kế theo **Star Schema** nhằm đơn giản hóa các truy vấn phân tích.

 Mô hình tổng quát:

```
                    dim_date
                       │
                       │
dim_customer ───── fact_sales ───── dim_product
                       │
                       │
                dim_salesperson
                       │
                       │
                 dim_territory
```

 ## Fact Tables

 Fact tables lưu các sự kiện nghiệp vụ có thể đo lường, ví dụ:

 - Sales
- Sales Order
- Inventory
- Purchasing

 ## Dimension Tables

 Dimension tables cung cấp thông tin mô tả cho các fact:

 - Customer
- Product
- Date
- Salesperson
- Territory
- Employee
- Product Category
- Product Subcategory

---

 # 9\. JSONB cho dữ liệu bán cấu trúc

 Một số thông tin liên quan đến **Sales Reason** có quan hệ một-nhiều với giao dịch bán hàng.

 Thay vì mở rộng thêm nhiều JOIN trên các bảng sự kiện, dữ liệu này được lưu dưới dạng `JSONB` trong bảng fact.

 Ví dụ:

```
[
  {
    "reason": "Price",
    "type": "Other"
  },
  {
    "reason": "Quality",
    "type": "Other"
  }
]
```

 Cách tiếp cận này giúp giữ các thông tin bán cấu trúc trực tiếp trên bản ghi fact và thuận tiện cho các truy vấn phân tích cần thông tin Sales Reason.

---

 # 10\. Data Quality

 Data Quality được kiểm tra trong quá trình Silver và Gold processing.

 ### Completeness

 - Kiểm tra NULL.
- Kiểm tra các trường bắt buộc.
- Kiểm tra dimension bị thiếu.

 ### Uniqueness

 - Phát hiện duplicate records.
- Kiểm tra duplicate business keys.

 ### Consistency

 - Kiểm tra data type.
- Chuẩn hóa text.
- Chuẩn hóa date format.

 ### Referential Integrity

 Kiểm tra quan hệ giữa Fact và Dimension:

```
fact_sales
    │
    ├── customer_key ──────► dim_customer
    │
    ├── product_key ───────► dim_product
    │
    ├── date_key ──────────► dim_date
    │
    └── salesperson_key ───► dim_salesperson
```

---

 # 11\. Apache Airflow

 Apache Airflow được sử dụng để điều phối toàn bộ pipeline batch.

 Luồng xử lý chính:

```
                 Start
                   │
                   ▼
          Extract SQL Server
                   │
                   ▼
          Write Bronze / Parquet
                   │
                   ▼
          Spark Silver Processing
                   │
          ┌────────┴────────┐
          ▼                 ▼
    Data Quality          SCD Type 2
          │                 │
          └────────┬────────┘
                   ▼
          Spark Gold Processing
                   │
                   ▼
         PostgreSQL Data Warehouse
                   │
                   ▼
          Analytics / Dashboard
```

 Airflow chịu trách nhiệm:

 - Scheduling.
- Dependency management.
- Retry khi task thất bại.
- Theo dõi trạng thái pipeline.
- Điều phối các bước ingestion và transformation.

---

 # 12\. Phân tích dữ liệu

 Sau khi dữ liệu được đưa vào Gold layer, hệ thống thực hiện các nhóm phân tích chính.

 ## 12.1. Sales Analytics

 Các metrics chính:

 - Total Revenue
- Gross Revenue
- Average Order Value
- Sales Growth
- Discount
- Freight
- Gross Margin
- Sales by Channel
- Sales by Time
- Sales by Territory

 Phân tích giúp theo dõi biến động doanh thu theo:

```
Year
Quarter
Month
Day
Territory
Sales Channel
Product
```

---

 # 13\. Customer Analytics

 ## Cohort Retention

 Phân tích cohort được sử dụng để theo dõi tỷ lệ khách hàng quay lại sau lần mua đầu tiên.

```
Cohort
   │
   ├── Month 0
   ├── Month 1
   ├── Month 2
   ├── ...
   └── Month N
```

 Các chỉ số được sử dụng để đánh giá:

 - Customer Retention
- Repeat Purchase
- Customer Churn
- Customer Reactivation

---

 # 14\. RFM + K-Means Customer Segmentation

 Khách hàng được tổng hợp thành các đặc trưng hành vi:

```
Total Orders
Total Spent
Average Order Value
Total Quantity
Distinct Products
Recency
Average Discount
```

 Các biến có phân phối lệch được biến đổi bằng:

```
log1p(x) = ln(1 + x)
```

 Sau đó chuẩn hóa bằng `StandardScaler`.

 K-Means được sử dụng để phân nhóm khách hàng.

 Các nhóm có thể được diễn giải thành:

```
New Customers
        │
        ▼
Low-value / Churn-risk
        │
        ▼
One-time High-value
        │
        ▼
Regular Customers
        │
        ▼
High-value Customers
```

 Mục đích của segmentation là hỗ trợ các chiến lược:

 - Customer retention.
- Win-back campaigns.
- Personalized marketing.
- Customer value analysis.

---

 # 15\. ABC Product Analysis

 ABC Analysis được sử dụng để phân loại sản phẩm dựa trên đóng góp doanh thu.

```
A → ~80% doanh thu
B → ~15% doanh thu
C → ~5% doanh thu
```

 Kết quả được sử dụng để phân tích:

 - Revenue concentration.
- Product portfolio.
- Inventory prioritization.
- Slow-moving products.
- Product profitability.

---

 # 16\. Inventory Analytics

 Các chỉ số được phân tích:

 - Current Inventory
- Inventory Value
- Sales Quantity
- Inventory Turnover
- Stock-out Risk
- Slow-moving Inventory

 Kết hợp ABC Analysis với inventory metrics giúp xác định các sản phẩm:

```
High Revenue
+
High Inventory
+
Low Turnover
        │
        ▼
Potential Capital Lock-up
```

 và:

```
High Demand
+
Low Inventory
        │
        ▼
Potential Stock-out Risk
```

---

 # 17\. Employee Performance Analytics

 Đối với Sales Person, hệ thống phân tích:

 - Total Revenue
- Number of Orders
- Average Order Value
- Sales Contribution
- Quota Performance

 Từ đó có thể theo dõi mức độ đóng góp của từng nhân viên và mức độ tập trung doanh thu trong đội ngũ Sales.

---

 # 18\. Streamlit Dashboard

 Kết quả phân tích được cung cấp thông qua Streamlit Dashboard.

 Dashboard bao gồm các nhóm:

```
┌─────────────────────────────────────────┐
│             Sales Dashboard             │
│ Revenue | AOV | Growth | Channel        │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│           Customer Dashboard            │
│ RFM | Cohort | Retention | Segmentation │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│         Product & Inventory             │
│ ABC | Margin | Inventory | Turnover     │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│         Employee Performance            │
│ Revenue | Orders | Quota | Contribution │
└─────────────────────────────────────────┘
```

---

 # 19\. Cấu trúc Project

```
adventureworks-olap-pipeline/
│
├── dags/
│   └── airflow DAGs
│
├── spark/
│   ├── bronze/
│   ├── silver/
│   └── gold/
│
├── sql/
│   ├── ddl/
│   ├── transformations/
│   └── analytics/
│
├── dashboard/
│   └── streamlit/
│
├── config/
│
├── scripts/
│
├── docker-compose.yml
│
└── README.md
```

 > Cấu trúc trên cần được điều chỉnh lại theo cấu trúc thực tế của repository nếu tên folder trong project khác.

---

 # 20\. Cách chạy

 ### Yêu cầu

 - Docker
- Docker Compose
- Git
- SQL Server AdventureWorks database

 Clone repository:

```
git clone https://github.com/hoangphuonglxag/adventureworks-olap-pipeline.git

cd adventureworks-olap-pipeline
```

 Khởi động các service:

```
docker compose up -d
```

 Kiểm tra:

```
docker compose ps
```

 Sau đó chạy pipeline thông qua Airflow.

 Luồng dữ liệu:

```
SQL Server
    ↓
Airflow
    ↓
MinIO Bronze
    ↓
Apache Spark
    ↓
Silver
    ↓
Apache Spark
    ↓
PostgreSQL Gold
    ↓
Streamlit
```

---

 # 21\. Kết quả chính

 Project thể hiện một pipeline Data Engineering end-to-end:

```
                    OLTP
                     │
                     ▼
              Data Ingestion
                     │
                     ▼
              Bronze / MinIO
                     │
                     ▼
           Spark Transformation
                     │
                     ▼
              Silver Layer
                     │
                     ▼
          Data Warehouse Modeling
                     │
                     ▼
              Gold / PostgreSQL
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
    Advanced Analytics     BI Dashboard
          │                     │
     ┌────┼────┐                │
     ▼    ▼    ▼                ▼
    RFM  ABC  Cohort        Streamlit
     │    │    │
     └────┴────┘
          │
          ▼
    Business Insights
```

 ### Các kỹ năng chính được áp dụng

 - Data Ingestion
- ETL / ELT
- Batch Data Pipeline
- Medallion Architecture
- Distributed Processing
- Data Warehouse
- Star Schema
- SCD Type 2
- Data Quality
- Apache Airflow
- Apache Spark
- MinIO
- PostgreSQL
- Docker
- RFM Analysis
- K-Means Clustering
- ABC Analysis
- Business Analytics

---

 # 22\. Repository

 **GitHub:**\
 https://github.com/hoangphuonglxag/adventureworks-olap-pipeline
