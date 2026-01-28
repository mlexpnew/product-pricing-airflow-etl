import requests 
import psycopg2
import os 
import logging
from datetime import date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
EXCHANGE_RATE_API_URL = "https://api.frankfurter.app/latest"
BASE_CURRENCY = "GBP"
TARGET_CURRENCY = "INR"

def get_db_connection():
    return psycopg2.connect(
        host="postgres",      # Docker service name
        port=5432,            # internal container port
        database="postgres",
        user="postgres",
        password="postgres"
    )


def fetch_exchange_rate() -> float:
    params = {
        "from": BASE_CURRENCY,
        "to": TARGET_CURRENCY
    }

    response = requests.get(EXCHANGE_RATE_API_URL, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    # Defensive validation
    if "rates" not in data or TARGET_CURRENCY not in data["rates"]:
        raise ValueError(f"Unexpected API response: {data}")

    rate = data["rates"][TARGET_CURRENCY]
    logger.info(f"Fetched exchange rate GBP → INR: {rate}")

    return rate

def store_exchange_rate(rate: float):
    conn = get_db_connection()
    cursor = conn.cursor()
    insert_query = """
    INSERT INTO staging_exchange_rates (rate_date, gbp_to_inr)
        VALUES (%s, %s)
        ON CONFLICT (rate_date)
        DO UPDATE SET
            gbp_to_inr = EXCLUDED.gbp_to_inr,
            fetched_at = CURRENT_TIMESTAMP;
    """
    today = date.today()
    cursor.execute(insert_query, (today, rate))
    conn.commit()
    cursor.close()
    conn.close()
    logger.info(f"Stored exchange rate for {today}")
    
def run():
    rate = fetch_exchange_rate()
    store_exchange_rate(rate)
    
if __name__ == "__main__":
    run()   
    

    