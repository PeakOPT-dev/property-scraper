"""
Florida Property Scraper Backend - Pinellas County
UPDATED: Jan 2026 - Uses Playwright for JS-rendered sites
FIXED: Endpoint paths, port handling, data extraction
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import re
import os

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

def scrape_pinellas_property(address):
    """
    Scrapes Pinellas County Property Appraiser using Playwright
    """
    print(f"\n=== Starting scrape for: {address} ===")

    # Clean Address
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

    try:
        with sync_playwright() as p:
            # Launch browser with proper args for Render
            browser = p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            page = browser.new_page()
            page.set_default_timeout(60000)  # 60 second timeout

            # Navigate to search URL
            base_url = "https://www.pcpao.gov/quick-search"
            final_url = f"{base_url}?qu=1&input={clean_address}&search_option=address"
            
            print(f"Navigating to: {final_url}")
            page.goto(final_url, wait_until='networkidle')

            # Wait for results to load
            print("Waiting for page to render...")
            try:
                page.wait_for_selector("table, text='Parcel Number'", timeout=20000)
            except Exception as e:
                print(f"Timeout waiting for page: {e}")
                browser.close()
                return {"error": "Page load timeout - county site may be slow", "status": "error"}

            # Get rendered HTML
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')

            # Check if we have results table or detail page
            results_table = soup.find('table')
            has_parcel_text = bool(soup.find(string=re.compile('Parcel Number', re.I)))
            
            if results_table and not has_parcel_text:
                # We're on results page - click first result
                print("On results page, looking for property link...")
                link_found = False
                
                for row in results_table.find_all('tr')[1:]:  # Skip header
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        # Look for link in Name or Parcel column
                        link = cells[0].find('a') or cells[1].find('a')
                        if link and 'href' in link.attrs:
                            href = link['href']
                            if not href.startswith('http'):
                                href = "https://www.pcpao.gov" + href
                            
                            print(f"Clicking result: {href}")
                            page.goto(href, wait_until='networkidle')
                            html_content = page.content()
                            soup = BeautifulSoup(html_content, 'html.parser')
                            link_found = True
                            break
                
                if not link_found:
                    browser.close()
                    return {"error": "No property found in search results", "status": "error"}
            
            elif has_parcel_text:
                print("Already on property detail page")
            else:
                browser.close()
                return {"error": "Could not locate property data", "status": "error"}

            # Extract data from detail page
            def find_table_value(label):
                """Find value in table by label"""
                for td in soup.find_all('td'):
                    if label.lower() in td.get_text().lower():
                        next_td = td.find_next_sibling('td')
                        if next_td:
                            return next_td.get_text(strip=True)
                return "Not found"

            # Basic info
            parcel_id = find_table_value('Parcel Number')
            owner = find_table_value('Owner Name')
            property_type = find_table_value('Property Use')
            site_address = find_table_value('Site Address')
            if site_address == "Not found":
                site_address = address
            legal_desc = find_table_value('Legal Description')
            year_built = find_table_value('Year Built')
            
            # Square footage
            living_sf = "Not found"
            gross_sf = "Not found"
            living_units = "Not found"
            
            for td in soup.find_all('td'):
                text = td.get_text(strip=True)
                if text == 'Living SF':
                    next_td = td.find_next_sibling('td')
                    living_sf = next_td.get_text(strip=True) if next_td else "Not found"
                elif text == 'Gross SF':
                    next_td = td.find_next_sibling('td')
                    gross_sf = next_td.get_text(strip=True) if next_td else "Not found"
                elif 'Living Units' in text:
                    next_td = td.find_next_sibling('td')
                    living_units = next_td.get_text(strip=True) if next_td else "Not found"

            # Values from Final Values table
            market_value = "Not found"
            assessed_value = "Not found"
            taxable_value = "Not found"
            
            # Look for "Final Values" or similar header
            for header in soup.find_all(['h2', 'h3', 'h4']):
                if 'final values' in header.get_text().lower() or 'values' in header.get_text().lower():
                    value_table = header.find_next('table')
                    if value_table:
                        rows = value_table.find_all('tr')
                        for row in rows:
                            cells = row.find_all('td')
                            if len(cells) >= 4:
                                first_cell = cells[0].get_text(strip=True)
                                # Look for current year (2025, 2026, etc)
                                if first_cell.isdigit() and len(first_cell) == 4:
                                    market_value = cells[1].get_text(strip=True)
                                    assessed_value = cells[2].get_text(strip=True)
                                    taxable_value = cells[3].get_text(strip=True) if len(cells) > 3 else "Not found"
                                    break
                    if market_value != "Not found":
                        break

            # Sale history
            last_sale_date = "Not found"
            last_sale_price = "Not found"
            
            for header in soup.find_all(['h2', 'h3', 'h4']):
                if 'sales history' in header.get_text().lower():
                    sales_table = header.find_next('table')
                    if sales_table:
                        rows = sales_table.find_all('tr')
                        for row in rows[1:]:  # Skip header
                            cells = row.find_all('td')
                            if len(cells) >= 2:
                                date_text = cells[0].get_text(strip=True)
                                if date_text and 'Sale Date' not in date_text:
                                    last_sale_date = date_text
                                    last_sale_price = cells[1].get_text(strip=True)
                                    break
                    if last_sale_date != "Not found":
                        break

            # Lot size
            lot_size = "Not found"
            land_text = soup.find(string=re.compile(r'Land Area:', re.I))
            if land_text:
                match = re.search(r'≅\s*([\d,]+)\s*sf', str(land_text))
                if match:
                    lot_size = f"{match.group(1)} sq ft"

            # Additional fields
            tax_district = find_table_value('Current Tax District')
            flood_zone = find_table_value('Flood Zone')

            # Compile results
            data = {
                "status": "success",
                "address": site_address,
                "parcelId": parcel_id,
                "owner": owner,
                "propertyType": property_type,
                "legalDescription": legal_desc,
                "yearBuilt": year_built,
                "livingArea": f"{living_sf} sq ft" if living_sf != "Not found" else living_sf,
                "grossArea": f"{gross_sf} sq ft" if gross_sf != "Not found" else gross_sf,
                "lotSize": lot_size,
                "livingUnits": living_units,
                "marketValue": market_value,
                "assessedValue": assessed_value,
                "taxableValue": taxable_value,
                "lastSaleDate": last_sale_date,
                "lastSalePrice": last_sale_price,
                "taxDistrict": tax_district,
                "floodZone": flood_zone,
                "roofType": "N/A",
                "county": "Pinellas",
                "sourceUrl": page.url
            }
            
            print(f"Scrape successful! Owner: {owner}, Parcel: {parcel_id}")
            browser.close()
            return data

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {"error": f"Scraping error: {str(e)}", "status": "error"}


@app.route('/api/search', methods=['POST'])
def search_property():
    """Main search endpoint"""
    data = request.json
    address = data.get('address')
    county = data.get('county', '').lower()
    
    if not address:
        return jsonify({"error": "Address required"}), 400
    
    if county and county != 'pinellas':
        return jsonify({"error": "Only Pinellas County supported", "status": "error"}), 400

    print(f"\n{'='*60}")
    print(f"API Request: {address} in {county}")
    print(f"{'='*60}")
    
    result = scrape_pinellas_property(address)
    return jsonify(result)


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "running",
        "message": "Playwright scraper active",
        "engine": "playwright",
        "supported_counties": ["Pinellas"]
    })


@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Test with known address"""
    print("\n=== TEST ENDPOINT ===")
    result = scrape_pinellas_property("1505 MAPLE ST")
    return jsonify(result)


@app.route('/', methods=['GET'])
def home():
    """Root endpoint"""
    return jsonify({
        "message": "Florida Property Scraper API v2.0",
        "engine": "Playwright (headless browser)",
        "endpoints": {
            "health": "/api/health",
            "test": "/api/test",
            "search": "/api/search (POST)"
        }
    })


if __name__ == '__main__':
    # Render uses PORT env variable
    port = int(os.environ.get('PORT', 5000))
    print(f"\n{'='*60}")
    print(f"🏠 Florida Property Scraper - Playwright Edition")
    print(f"{'='*60}")
    print(f"Starting on port {port}")
    print(f"{'='*60}\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)
