# Product Pricing ETL Pipeline (Airflow + Docker)

## 📌 Problem Statement
Build an end-to-end data pipeline that:
- Scrapes product data from a public website
- Fetches live exchange rates
- Transforms pricing data
- Loads analytics-ready data into PostgreSQL
- Orchestrates the workflow using Apache Airflow
- Runs fully via Docker

---

## 🏗️ Solution Overview
This project implements a **daily ETL pipeline** using:
- **Python** for scraping & transformations
- **PostgreSQL** for storage
- **Apache Airflow** for orchestration
- **Docker & Docker Compose** for containerization

---

## 🔄 Pipeline Flow
Scrape Products
↓
Fetch Exchange Rate (GBP → INR)
↓
Transform Product Data
↓
Load into PostgreSQL


---

## 📂 Project Structure

data-pipeline/
├── dags/
│ └── product_pricing_dag.py
├── scripts/
│ ├── scrape_products.py
│ ├── fetch_exchange_rate.py
│ ├── transform_products.py
│ └── load_products.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md


---

## ⚙️ Tech Stack
- Python 3
- Apache Airflow 2.x
- PostgreSQL
- Docker & Docker Compose

---

## 🚀 How to Run the Project

### 1️⃣ Prerequisites
- Docker Desktop installed and running

---

### 2️⃣ Start the Pipeline
From the project root:

```bash
docker compose up -d

3️⃣ Access Airflow UI

URL: http://localhost:8080
Username: admin
Password: admin

Run the DAG
Enable product_pricing_pipeline
Trigger the DAG manually
Monitor task execution (all tasks should turn green)


Database Tables
staging_exchange_rates
Column	Description
rate_date	Exchange rate date
gbp_to_inr	GBP → INR rate
fetched_at	Timestamp

products
Column	Description
product_id	Hashed unique ID
title	Product title
category	Normalized category
availability_count	Stock count
price_gbp	Price in GBP
price_inr	Converted price
price_tier	cheap / moderate / expensive
load_date	Load date


Verify Data Load
docker exec -it postgres psql -U postgres -d postgres

SELECT COUNT(*) FROM products;
SELECT * FROM staging_exchange_rates ORDER BY rate_date DESC LIMIT 5;


Scheduling
DAG runs daily (@daily)
Retries enabled for fault tolerance

Key Design Decisions
Idempotent loads using UPSERT logic
Separation of concerns (scrape / transform / load)
Dockerized Airflow for reproducibility
Explicit Python path handling for Airflow imports


Future Improvements
Add data quality checks
Add alerts on DAG failures
Secure secrets using Airflow Connections
Add unit tests
