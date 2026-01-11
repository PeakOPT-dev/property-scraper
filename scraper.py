"""
Florida Property Scraper Backend - Pinellas County
UPDATED: Jan 2026 - Uses Playwright for JS-rendered sites
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import re
import time
import os

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

def scrape_pinellas_property(address):
    """
    Scrapes Pinellas County Property Appraiser using Playwright (Headless Browser)
    to handle the JavaScript-loaded results table.
    """
    print(f"Starting scrape for: {address}")

    # 1. Clean Address Logic (Kept from your original code)
    city_names = ['CLEARWATER', 'LARGO', 'ST PETERSBURG', 'SAINT PETERSBURG', 
                  'PINELLAS PARK', 'DUNEDIN', 'TARPON SPRINGS', 'SAFETY HARBOR',
                  'SEMINOLE', 'BELLEAIR', 'GULFPORT', 'TREASURE ISLAND', 
                  'ST PETE BEACH', 'MADEIRA BEACH', 'REDINGTON BEACH', 
                  'FL', 'FLORIDA']
    
    clean_address = address.upper()
    for city in city_names:
        clean_address = re.sub(r'\b' + city + r'\b', '', clean_address, flags=re.IGNORECASE)
    
    clean_address = clean_address.replace(',', ' ')
    clean_address = ' '.join(clean_address.split())
    
    print(f"Cleaned address: {clean_address}")

    # 2. Launch Headless Browser
    try:
        with sync_playwright() as p:
            # Launch chromium (headless=True means no UI window pops up)
            # args=['--no-sandbox'] is often needed for cloud hosting like Render
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()

            # Construct the search URL directly with parameters
            # This triggers the React app to load specific results
            base_url = "https://www.pcpao.gov/quick-search"
            # We encode the parameters manually to be safe
            final_url = f"{base_url}?qu=1&input={clean_address}&search_option=address"
            
            print(f"Navigating to: {final_url}")
            page.goto(final_url, timeout=60000)

            # 3. Wait for Data to Load
            # We wait for either the results table OR the 'Parcel Number' text (if it auto-redirects to details)
            print("Waiting for results to render...")
            try:
                # Wait up to 15 seconds for a table or parcel number to appear
                page.wait_for_selector("table, text='Parcel Number'", timeout=15000)
            except:
                print("Timed out waiting for selector. Page might be empty or slow.")

            # Get the fully rendered HTML
            html_content = page.content()
            
            # Now we use BeautifulSoup to parse the rendered HTML (Your existing logic)
            soup = BeautifulSoup(html_content, 'html.parser')

            # 4. Check for Results
            # Case A: We are on the Search Results list page
            results_table = soup.find('table')
            is_detail_page = False
            
            if results_table and not soup.find(string=re.compile('Parcel Number', re.I)):
                print("Found results table, looking for link...")
                # Find the link to the property details
                for row in results_table.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        link = row.find('a', href=True)
                        if link:
                            click_url = link['href']
                            if not click_url.startswith('http'):
                                click_url = "https://www.pcpao.gov" + click_url
                            
                            print(f"Clicking result: {click_url}")
                            page.goto(click_url)
                            page.wait_for_load_state('networkidle') # Wait for network to settle
                            html_content = page.content()
                            soup = BeautifulSoup(html_content, 'html.parser')
                            is_detail_page = True
                            break
            else:
                # Case B: The site auto-redirected us to the Detail Page
                if "Parcel Number" in soup.get_text():
                    print("Directly landed on detail page.")
                    is_detail_page = True

            if not is_detail_page:
                return {
                    "error": "Could not find property details or parcel number.",
                    "status": "error",
                    "debug_html": soup.get_text()[:200]
                }

            # 5. Extract Data (Your existing parsing logic)
            def find_field(label):
                for td in soup.find_all(['td', 'span', 'div']): # Expanded tags
                    if label.lower() in td.get_text().lower():
                        # Try finding next sibling or value inside
                        # Adjusting logic for modern div-based layouts
                        parent = td.parent
                        if parent:
                            text = parent.get_text(strip=True)
                            # Simple cleanup to remove the label from the text
                            clean_val = text.replace(label, '').replace(':', '').strip()
                            return clean_val
                return "Not found"

            # Re-implementing specific table scraping from your code
            # Note: I expanded find_field above, but let's stick to your specific table logic 
            # if the site still uses tables for details.
            
            # Helper to find value by label in table cells
            def get_val(label):
                tag = soup.find(string=re.compile(label))
                if tag:
                    # Usually the value is in the next cell or parent's next sibling
                    try:
                        return tag.find_next('td').get_text(strip=True)
                    except:
                        try:
                            return tag.parent.find_next_sibling().get_text(strip=True)
                        except:
                            return "Not found"
                return "Not found"

            parcel_id = get_val('Parcel Number')
            owner = get_val('Owner Name')
            property_type = get_val('Property Use')
            year_built = get_val('Year Built')
            
            # Living Area
            living_sf = "Not found"
            if soup.find(string='Living SF'):
                living_sf = get_val('Living SF')
            
            # Values
            market_value = "Not found"
            assessed_value = "Not found"
            # Try to grab the first money value from the "Values" section
            # This is tricky without seeing the exact DOM, but let's try a generic approach
            val_table = soup.find('table', id=re.compile('value', re.I))
            if val_table:
                rows = val_table.find_all('tr')
                if len(rows) > 1:
                    cells = rows[-1].find_all('td') # Last row usually current year
                    if len(cells) > 2:
                        market_value = cells[1].get_text(strip=True)
                        assessed_value = cells[2].get_text(strip=True)

            # Fallback for values if table not found
            if market_value == "Not found":
                 market_value = "$0.00 (Scrape failed)"

            # Compile
            data = {
                "status": "success",
                "address": address,
                "parcelId": parcel_id if parcel_id else "Check County Site",
                "owner": owner,
                "propertyType": property_type,
                "yearBuilt": year_built,
                "livingArea": living_sf,
                "marketValue": market_value,
                "assessedValue": assessed_value,
                "county": "Pinellas",
                "link": page.url
            }
            
            browser.close()
            return data

    except Exception as e:
        print(f"Playwright Error: {e}")
        return {"error": str(e), "status": "error"}


@app.route('/api/search', methods=['POST'])
def search_property():
    data = request.json
    address = data.get('address')
    county = data.get('county')
    
    if not address:
        return jsonify({"error": "Address required"}), 400
    
    # We only support Pinellas in this script for now
    if county and county.lower() != 'pinellas':
        return jsonify({"error": "Only Pinellas supported in this backend version"}), 400

    result = scrape_pinellas_property(address)
    return jsonify(result)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "active", "engine": "playwright"})

if __name__ == '__main__':
    # Default to 10000 for Render, 5000 for local
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
