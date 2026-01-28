import psycopg2
from typing import List, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------- DB CONNECTION ----------
def get_db_connection():
    return psycopg2.connect(
        host="postgres",
        port="5432",
        database="postgres",
        user="postgres",
        password="postgres"
    )


# ---------- CREATE FINAL TABLE ----------
def create_products_table():
    conn = get_db_connection()
    cursor = conn.cursor()

    create_table_query = """
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            title TEXT,
            category TEXT,
            availability_count INTEGER,
            price_gbp NUMERIC,
            price_inr NUMERIC,
            price_tier TEXT,
            load_date DATE
        );
    """

    cursor.execute(create_table_query)
    conn.commit()

    cursor.close()
    conn.close()

    logger.info("Products table ensured")


# ---------- UPSERT PRODUCTS ----------
def load_products(products: List[Dict]):
    conn = get_db_connection()
    cursor = conn.cursor()

insert_query = """
    INSERT INTO products (
        product_id,
        title,
        category,
        availability_count,
        price_gbp,
        price_inr,
        price_tier,
        load_date
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (product_id)
    DO UPDATE SET
        title = EXCLUDED.title,
        category = EXCLUDED.category,
        availability_count = EXCLUDED.availability_count,
        price_gbp = EXCLUDED.price_gbp,
        price_inr = EXCLUDED.price_inr,
        price_tier = EXCLUDED.price_tier,
        load_date = EXCLUDED.load_date;
"""

for product in products:
    cursor.execute(insert_query, (
        product["product_id"],
        product["title"],
        product["category"],
        product["availability_count"],
        product["price_gbp"],
        product["price_inr"],
        product["price_tier"],
        date.today()
    ))
   


    conn.commit()
    cursor.close()
    conn.close()

    logger.info(f"Loaded {len(products)} products into final table")
