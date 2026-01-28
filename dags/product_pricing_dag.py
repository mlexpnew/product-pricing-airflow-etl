import sys
sys.path.insert(0, "/opt/airflow/scripts")

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

from scrape_products import scrape_products
from fetch_exchange_rate import run as fetch_exchange_rate
from transform_products import transform_products
from load_products import load_products


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}


def scrape_task(**context):
    products = scrape_products()
    context["ti"].xcom_push(key="raw_products", value=products)


def transform_task(**context):
    raw_products = context["ti"].xcom_pull(
        key="raw_products", task_ids="scrape_products"
    )
    transformed = transform_products(raw_products)
    context["ti"].xcom_push(key="transformed_products", value=transformed)


def load_task(**context):
    products = context["ti"].xcom_pull(
        key="transformed_products", task_ids="transform_products"
    )
    load_products(products)


with DAG(
    dag_id="product_pricing_pipeline",
    default_args=default_args,
    description="Daily product pricing ETL pipeline",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    tags=["etl", "pricing"],
) as dag:

    scrape_products_task = PythonOperator(
        task_id="scrape_products",
        python_callable=scrape_task,
        provide_context=True,
    )

    fetch_exchange_rate_task = PythonOperator(
        task_id="fetch_exchange_rate",
        python_callable=fetch_exchange_rate,
    )

    transform_products_task = PythonOperator(
        task_id="transform_products",
        python_callable=transform_task,
        provide_context=True,
    )

    load_products_task = PythonOperator(
        task_id="load_products",
        python_callable=load_task,
        provide_context=True,
    )

    # Task dependencies
    scrape_products_task >> fetch_exchange_rate_task >> transform_products_task >> load_products_task
