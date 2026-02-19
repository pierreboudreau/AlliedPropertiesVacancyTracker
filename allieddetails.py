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
#driver= webdriver.Chrome(options=chrome_options)
driver.set_page_load_timeout(90) 




# Dynamic date
today = datetime.now().strftime("%Y-%m-%d")
input_file = f"data/allied_{today}.json"
output_file = f"data/allied_{today}_updated.json"

# Load the JSON
try:
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    log(f"Input file {input_file} not found")
    driver.quit()
    exit()

properties = data.get('properties', [])
updated_properties = []
skipped = []

# Optional: Save after each property (set to False or comment out to disable)
save_after_each = True

for prop in properties:
    updated_prop = prop.copy()
    if prop['available_suites'] > 0:
        link = prop['link']
        print(f"Scraping suites for {prop['name']} at {link}")
        for attempt in range(2):  # Retry once
            try:
                driver.get(link)
                wait = WebDriverWait(driver, 20)  # Increased wait time
                # Handle cookie prompt on detail page
                try:
                    accept_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".trustarc-acceptall-btn")))
                    accept_btn.click()
                    print(f"Cookie prompt accepted on detail page for {prop['name']}")
                except (TimeoutException, NoSuchElementException):
                    print(f"No cookie prompt on detail page for {prop['name']}")
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                # Scroll the detail page to load any lazy content
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(8)  # Slight increase

                # Try to expand table rows if present
                try:
                    table = driver.find_element(By.TAG_NAME, 'table')
                    rows = table.find_elements(By.TAG_NAME, 'tr')
                    for row in rows:
                        try:
                            row.click()
                            time.sleep(1)
                        except Exception:
                            pass
                except Exception:
                    print(f"No table to expand for {prop['name']}")

                time.sleep(30)  # Increased wait for JS and to avoid stalls
                detail_soup = BeautifulSoup(driver.page_source, 'html.parser')

                suites = []
                available_sqft = 0

                # Find availability section
                avail_h2 = detail_soup.find('h2', string=re.compile(r'Availability', re.I))
                if avail_h2:
                    # Try table parsing first
                    table = avail_h2.find_next('table')
                    if table:
                        rows = table.find_all('tr')
                        i = 0
                        while i < len(rows):
                            row = rows[i]
                            tds = row.find_all('td')
                            if len(tds) >= 4:
                                suite = {}
                                suite_number_str = tds[0].text.strip()
                                suite['suite_number'] = re.sub(r'^[v^]\s*', '', suite_number_str)
                                suite['type'] = tds[1].text.strip()
                                size_str = tds[2].text.strip().replace(' SF', '').replace(',', '')
                                suite['sq_ft'] = int(size_str) if size_str.isdigit() else 0
                                available_sqft += suite['sq_ft']
                                suite['availability'] = tds[3].text.strip()
                                suite['net_rent'] = 'Unknown'
                                suite['additional_rent'] = 'Unknown'
                                # Check if next row is expanded
                                i += 1
                                if i < len(rows) and len(rows[i].find_all('td')) == 1:
                                    expanded_td = rows[i].find('td')
                                    p_elems = expanded_td.find_all('p')
                                    details = {}
                                    for j in range(0, len(p_elems), 2):
                                        if j+1 < len(p_elems):
                                            label = p_elems[j].text.strip().rstrip(':').lower()
                                            value = p_elems[j+1].text.strip()
                                            if label == 'net rent':
                                                suite['net_rent'] = value
                                            if label == 'additional rent':
                                                suite['additional_rent'] = value
                                    i += 1
                                else:
                                    i -= 1  # No expanded, adjust back
                                if suite['sq_ft'] > 0:
                                    suites.append(suite)
                            else:
                                i += 1
                    else:
                        # Fall back to h3/p with class logic
                        h3_elems = avail_h2.find_all_next('h3', class_='number')
                        if h3_elems:
                            for h3 in h3_elems:
                                suite = {}
                                suite['suite_number'] = h3.text.strip()
                                suite_div = h3.find_parent('div')
                                p_type = suite_div.find('p', class_='type')
                                suite['type'] = p_type.text.strip() if p_type else 'Unknown'
                                p_size = suite_div.find('p', class_='size')
                                size_value = p_size.text.strip() if p_size else '0 SF'
                                sq_ft_str = re.sub(r'[^\d]', '', size_value.split(' ')[0])
                                sq_ft = int(sq_ft_str) if sq_ft_str.isdigit() else 0
                                suite['sq_ft'] = sq_ft
                                if sq_ft > 0:
                                    available_sqft += sq_ft
                                p_avail = suite_div.find('p', class_='avail')
                                suite['availability'] = p_avail.text.strip() if p_avail else 'Unknown'
                                # Guess for net rent and additional rent classes
                                p_net = suite_div.find('p', class_='net') or suite_div.find('p', class_='rent') or suite_div.find('p', string=re.compile(r'Net Rent:\s*', re.I))
                                suite['net_rent'] = p_net.text.strip() if p_net else 'Unknown'
                                p_additional = suite_div.find('p', class_='additional') or suite_div.find('p', class_='additional-rent') or suite_div.find('p', string=re.compile(r'Additional Rent:\s*', re.I))
                                suite['additional_rent'] = p_additional.text.strip() if p_additional else 'Unknown'
                                suites.append(suite)
                        else:
                            # Fall back to h4 label logic if no h3 with class 'number'
                            h3_elems = avail_h2.find_all_next('h3')
                            first_h3 = h3_elems[0] if h3_elems else None

                            if first_h3 and 'suite #' in first_h3.text.lower():
                                # Generic suites, multiple groups by Type h4
                                type_h4s = avail_h2.find_all_next('h4', string=re.compile(r'^Type$', re.I))
                                for idx, type_h4 in enumerate(type_h4s, start=1):
                                    suite = {}
                                    suite['suite_number'] = f"Suite {idx}"
                                    details = {}
                                    current = type_h4
                                    while current:
                                        if current.name == 'h4':
                                            label = current.text.strip().rstrip(':').lower()
                                            value_elem = current.find_next_sibling('p')
                                            value = value_elem.text.strip() if value_elem else ''
                                            details[label] = value
                                        next_elem = current.find_next('h4')
                                        if next_elem and next_elem.text.strip().lower() == 'type':
                                            break
                                        current = next_elem
                                    if 'size' in details:
                                        suite['type'] = details.get('type', 'Unknown')
                                        size_value = details.get('size', '0 SF')
                                        sq_ft_str = re.sub(r'[^\d]', '', size_value.split(' ')[0])
                                        sq_ft = int(sq_ft_str) if sq_ft_str.isdigit() else 0
                                        suite['sq_ft'] = sq_ft
                                        if sq_ft > 0:
                                            available_sqft += sq_ft
                                        suite['availability'] = details.get('availability', 'Unknown')
                                        suite['net_rent'] = details.get('net rent', 'Unknown')
                                        suite['additional_rent'] = details.get('additional rent', 'Unknown')
                                        suites.append(suite)
                            else:
                                # Specific suite numbers with h3
                                for i, h3 in enumerate(h3_elems):
                                    suite = {}
                                    suite['suite_number'] = h3.text.strip()
                                    details = {}
                                    next_h3 = h3_elems[i+1] if i+1 < len(h3_elems) else None
                                    current = h3.find_next('h4')
                                    while current and (not next_h3 or current < next_h3):
                                        label = current.text.strip().rstrip(':').lower()
                                        value_elem = current.find_next_sibling('p')
                                        value = value_elem.text.strip() if value_elem else ''
                                        details[label] = value
                                        current = current.find_next('h4')
                                    if 'size' in details:
                                        suite['type'] = details.get('type', 'Unknown')
                                        size_value = details.get('size', '0 SF')
                                        sq_ft_str = re.sub(r'[^\d]', '', size_value.split(' ')[0])
                                        sq_ft = int(sq_ft_str) if sq_ft_str.isdigit() else 0
                                        suite['sq_ft'] = sq_ft
                                        if sq_ft > 0:
                                            available_sqft += sq_ft
                                        suite['availability'] = details.get('availability', 'Unknown')
                                        suite['net_rent'] = details.get('net rent', 'Unknown')
                                        suite['additional_rent'] = details.get('additional rent', 'Unknown')
                                        suites.append(suite)
                else:
                    print(f"No availability section found for {prop['name']}.")

                # Verify
                if len(suites) != prop['available_suites']:
                    print(f"Warning: Suite count mismatch for {prop['name']}: JSON says {prop['available_suites']}, found {len(suites)}")
                if available_sqft == 0 and suites:
                    print(f"Warning: Zero available_sqft for {prop['name']} despite {len(suites)} suites")

                updated_prop['available_sqft'] = available_sqft
                updated_prop['suites'] = suites
                print(f"Added {len(suites)} suites for {prop['name']}, total sqft: {available_sqft}")
                break

            except Exception as e:
                print(f"Error scraping suites for {prop['name']} (attempt {attempt + 1}/2): {str(e)}")
                if attempt == 1:
                    skipped.append({"name": prop['name'], "link": link, "reason": str(e)})
                    updated_prop['available_sqft'] = 0
                    updated_prop['suites'] = []
                    print(f"Skipped {prop['name']} after retries")
                time.sleep(5)  # Increased retry delay
    else:
        updated_prop['available_sqft'] = 0
        updated_prop['suites'] = []

    updated_properties.append(updated_prop)

    # Optionally save after each property
    if save_after_each:
        updated_data = {
            "date": data['date'],
            "properties": updated_properties,
            "skipped_properties": data.get('skipped_properties', []) + skipped
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(updated_data, f, indent=4)
        print(f"Intermediate JSON saved to {output_file} after processing {prop['name']}")

driver.quit()

updated_data = {
    "date": data['date'],
    "properties": updated_properties,
    "skipped_properties": data.get('skipped_properties', []) + skipped
}

with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(updated_data, f, indent=4)

input_file = f"data/allied_{today}_updated.json"
output_file = f"data/allied_{today}_cleaned.json"

# Load the JSON
with open(input_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Process each property
for prop in data.get('properties', []):
    if 'suites' in prop:
        # Filter out suites where suite_number is "Suite #"
        prop['suites'] = [suite for suite in prop['suites'] if suite.get('suite_number') != 'Suite #']

# Save the cleaned JSON
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4)

print(f"Cleaned JSON saved to {output_file}")

print(f"Updated JSON saved to {output_file}")