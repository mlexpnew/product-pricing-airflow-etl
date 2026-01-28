import requests
from bs4 import BeautifulSoup
from typing import List, Dict
import re
import logging 

BASE_URL = "https://books.toscrape.com/"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_category_from_product_page(product_url: str) -> str:
    try:
        response = requests.get(
            product_url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch category for {product_url}: {e}")
        return "unknown"

    soup = BeautifulSoup(response.text, 'html.parser')
    breadcrumb = soup.select('ul.breadcrumb li a')
    if len(breadcrumb) >= 3:
        return breadcrumb[2].text.strip().lower()
    return "unknown"
def scrape_products() -> List[Dict]:
    products = []
    page_url = "catalogue/page-1.html"
    while page_url:
        logger.info(f"Scraping page: {BASE_URL}{page_url}")
        resopnse = requests.get(f"{BASE_URL}{page_url}", timeout=10)
        resopnse.raise_for_status()
        soup = BeautifulSoup(resopnse.text, 'html.parser')
        articles = soup.select('article.product_pod')
        for article in articles:
            title = article.h3.a['title'].strip()
            price_text = article.select_one('p.price_color').text.strip()
            price_gbp = float(re.sub(r"[^\d.]", "", price_text))
            availability = article.select_one(".availability").text.strip()
            product_relative_url = article.h3.a['href']
            product_url = BASE_URL + "catalogue/" + product_relative_url
            category = get_category_from_product_page(product_url)
            products.append({
                "title": title,
                "price_gbp": price_gbp,
                "category": category,
                "availability": availability
            })

        next_button = soup.select_one("li.next a")
        page_url = "catalogue/" + next_button["href"] if next_button else None

    logger.info(f"Scraped {len(products)} products")
    return products
if __name__ == "__main__":
    data = scrape_produts()
    print(f"Total products scraped: {len(data)}")
    
    
                
            
            

                  