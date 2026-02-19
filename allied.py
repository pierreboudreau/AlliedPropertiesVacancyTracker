import os
import json
import time
import re
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service

# Set up Selenium
chrome_options = Options()
chrome_options.add_argument("--headless")  # Uncomment for headless
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")

service = Service(r"chromedriver.exe")
driver = webdriver.Chrome(service=service, options=chrome_options)
driver.set_page_load_timeout(90) 

def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")


# URL to scrape
list_url = "https://alliedreit.com/properties/"

# Load main page with retry
for attempt in range(2):
    try:
        driver.get(list_url)
        log("Page loaded")
        time.sleep(5)
        break
    except TimeoutException:
        log(f"Page load timeout, retrying ({attempt + 1}/2)...")
        time.sleep(3)
else:
    log("Page load failed after retries")
    driver.quit()
    exit()

# Cookie consent
try:
    wait = WebDriverWait(driver, 10)
    accept_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".trustarc-acceptall-btn")))
    accept_btn.click()
    log("Cookies accepted")
    time.sleep(3)
except (TimeoutException, NoSuchElementException):
    log("No cookie prompt or failed to accept")

# Scroll to load all properties
for _ in range(5):  # Scroll 5 times
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

# Check for properties
try:
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "article.item")))
    log("Properties detected")
except TimeoutException:
    log("No properties found. Logging source...")
    print(driver.page_source[:2000])
    driver.quit()
    exit()

# Parse page
soup = BeautifulSoup(driver.page_source, 'html.parser')
property_articles = soup.find_all('article', class_='item')
log(f"Found {len(property_articles)} articles")

properties = []
skipped_properties = []
expected_total = 168

for article in property_articles:
    try:
        # Name
        name_elem = article.find('h2')
        if not name_elem:
            log("Skipping article: No name found")
            skipped_properties.append({"reason": "No name"})
            continue
        name = name_elem.text.strip()

        # City
        city_elem = article.find('p', class_='paragraph-2 uppercase bold')
        city = city_elem.text.strip() if city_elem else ""
        if ',' in city:
            city = city.split(',')[-1].strip()
        if not city:
            log(f"Warning: Empty city for {name}")

        # Total GLA
        total_gla = 0
        gla_elem = article.find('p', class_='body', string=re.compile(r'\d+\s*SQ\.\s*FT\.\s*total GLA'))
        if gla_elem:
            gla_match = re.search(r'(\d{1,3}(,\d{3})*)', gla_elem.text.strip())
            if gla_match:
                total_gla = int(gla_match.group(1).replace(',', ''))
        else:
            # Fallback for variations
            gla_fallback = article.find(string=re.compile(r'\d+\s*(square feet|SQ\. FT\.)'))
            if gla_fallback:
                gla_match = re.search(r'(\d{1,3}(,\d{3})*)', gla_fallback.strip())
                if gla_match:
                    total_gla = int(gla_match.group(1).replace(',', ''))
                    log(f"Fallback GLA used for {name}: {total_gla}")
        if total_gla == 0:
            log(f"Warning: Empty total_gla for {name}")

        # Available suites
        available_suites = 0
        suites_elem = article.find('p', class_='body', string=re.compile(r'Suites available: \d+'))
        if suites_elem:
            suites_match = re.search(r'Suites available: (\d+)', suites_elem.text.strip())
            if suites_match:
                available_suites = int(suites_match.group(1))
        else:
            log(f"Warning: No suites found for {name}")

        # Link
        link_elem = article.find('a')
        link = link_elem['href'] if link_elem else ""
        if link and not link.startswith('http'):
            link = f"https://alliedreit.com{link}"
        if not link:
            log(f"Warning: Empty link for {name}")

        property_data = {
            "name": name,
            "city": city,  # Remove if not needed
            "total_gla": total_gla,
            "available_suites": available_suites,
            "link": link
        }

        properties.append(property_data)

    except Exception as e:
        log(f"Error processing article for {name or 'unknown'}: {e}")
        skipped_properties.append({"name": name or "unknown", "reason": str(e)})

driver.quit()

total_scraped = len(properties)
log(f"Total scraped: {total_scraped} (Expected ~168)")
if total_scraped < expected_total:
    log(f"Fewer than expected; check for missing articles or skips: {len(skipped_properties)}")

today = datetime.now().strftime("%Y-%m-%d")
data = {
    "date": today,
    "properties": properties,
    "skipped_properties": skipped_properties
}

os.makedirs('data', exist_ok=True)
filename = f"data/allied_{today}.json"
with open(filename, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4)

log(f"Saved to {filename}")
