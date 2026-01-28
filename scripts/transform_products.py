import psycopg2
import hashlib
from datetime import date
import logging
from typing import List, Dict
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#------DB CONNECTION FUNCTION------

def get_db_connection():
    return psycopg2.connect(
        host="postgres",
        port="5432",
        database="postgres",
        user="postgres",
        password="postgres"
        
    )
#------FEATCH LATEST EXCHANGE RATE-----

def fetch_latest_exchange_rate():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT gbp_to_inr
        FROM staging_exchange_rates
        ORDER BY rate_date DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        logger.warning("No exchange rate found, using fallback rate = 1.0")
        return 1.0

    return float(row[0])



# ---------- CLEAN & PARSE AVAILABILITY ----------
def parse_availability(text: str) -> int:
    match = re.search(r"\d+", text)
    return int(match.group()) if match else 0

#------PRICE TIER------
def derive_price_tier(price_in_inr: float) -> str:
    if price_in_inr < 500:
        return "cheap"
    elif 500 <= price_in_inr < 1500:
        return "moderate"
    else:
        return "expensive"
    

#------STABLE PRODUCT ID------
def generate_product_id(title: str, category: str, price_gbp: float) -> str:
    raw = f"{title}|{category}|{price_gbp}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

#------MAIN TRANSFORMATION  ------
def transform_products(raw_products: List[Dict]) -> List[Dict]:
    exchange_rate = fetch_latest_exchange_rate()
    logger.info(f"Using exchange rate: {exchange_rate}")
    transformed = []
    for product in raw_products:
        title = product["title"].strip()
        category = product["category"].strip().lower().replace(" ", "_")
        availability_count = parse_availability(product["availability"])
        
        price_gbp = float(product["price_gbp"])
        price_in_inr = round(price_gbp * exchange_rate, 2)
        price_tier = derive_price_tier(price_in_inr)
        product_id = generate_product_id(title, category, price_gbp)
        
        
        
        transformed.append({
            "product_id": product_id,
            "title": product["title"],
            "category": product["category"],
            "price_gbp": product["price_gbp"],
            "price_inr": price_in_inr,
            "price_tier": price_tier,
            "availability_count": availability_count
        })
    logger.info(f"Transformed {len(transformed)} products")
    return transformed
    





         
    

