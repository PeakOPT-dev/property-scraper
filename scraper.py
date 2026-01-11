"""
Florida Property Scraper Backend - Pinellas County
LATEST VERSION - Updated Jan 2026
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

def scrape_pinellas_property(address):
    """
    Scrapes Pinellas County Property Appraiser for property details
    """
    try:
        base_url = "https://www.pcpao.gov"
        search_url = f"{base_url}/quick-search"
        
        # Clean the address - remove city names that break the search
        # Pinellas search works with: "1505 MAPLE ST" or "1505 MAPLE ST 33755"
        # But FAILS with city names
        city_names = ['CLEARWATER', 'LARGO', 'ST PETERSBURG', 'SAINT PETERSBURG', 
                      'PINELLAS PARK', 'DUNEDIN', 'TARPON SPRINGS', 'SAFETY HARBOR',
                      'SEMINOLE', 'BELLEAIR', 'GULFPORT', 'TREASURE ISLAND', 
                      'ST PETE BEACH', 'MADEIRA BEACH', 'REDINGTON BEACH', 
                      'FL', 'FLORIDA']
        
        clean_address = address.upper()
        for city in city_names:
            clean_address = re.sub(r'\b' + city + r'\b', '', clean_address, flags=re.IGNORECASE)
        
        # Remove commas and extra spaces
        clean_address = clean_address.replace(',', ' ')
        clean_address = ' '.join(clean_address.split())
        
        print(f"Original address: {address}")
        print(f"Cleaned address: {clean_address}")
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        })
        
        # Perform search with cleaned address using CORRECT parameters
        params = {
            'qu': '1',
            'input': clean_address,
            'search_option': 'address'
        }
        response = session.get(search_url, params=params, timeout=30)
        
        print(f"Response status: {response.status_code}")
        print(f"Response URL: {response.url}")
        
        if response.status_code != 200:
            return {"error": f"County website returned status {response.status_code}", "status": "error"}
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        print(f"Looking for results table...")
        
        # Look for the results table with parcel numbers
        # The table has columns: Name, Parcel Number, Address, Tax Dist, Property Use
        results_table = soup.find('table')
        
        if results_table:
            print("Found results table")
            # Look for parcel number link in the table
            parcel_link = None
            
            for row in results_table.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 2:
                    # Second column should have parcel number with link
                    parcel_cell = cells[1]
                    link = parcel_cell.find('a', href=re.compile(r'parcel='))
                    if link:
                        parcel_link = link
                        print(f"Found parcel link: {link.get('href')}")
                        break
            
            if parcel_link:
                # Navigate to property details
                detail_url = parcel_link['href']
                if not detail_url.startswith('http'):
                    detail_url = base_url + detail_url
                
                print(f"Navigating to property details: {detail_url}")
                time.sleep(1)
                response = session.get(detail_url, timeout=30)
                soup = BeautifulSoup(response.content, 'html.parser')
                is_detail_page = True
            else:
                return {
                    "error": "No property found in search results",
                    "status": "error"
                }
        else:
            print("No results table found")
            # Check if already on detail page
            has_parcel = soup.find(string=re.compile('Parcel Number', re.I))
            has_owner = soup.find('td', string=re.compile('Owner Name', re.I))
            is_detail_page = '/property-details' in response.url or has_parcel or has_owner
            
            if not is_detail_page:
                return {
                    "error": "No property found for this address",
                    "status": "error",
                    "suggestion": "Try different format: '1505 MAPLE ST' or add ZIP"
                }
        
        # Now extract data from property detail page
        def find_field(label):
            """Find table cell value by label"""
            for td in soup.find_all('td'):
                if label.lower() in td.get_text().lower():
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        return next_td.get_text(strip=True)
            return "Not found"
        
        # Extract basic info
        parcel_id = find_field('Parcel Number')
        owner = find_field('Owner Name')
        property_type = find_field('Property Use')
        site_address = find_field('Site Address')
        if site_address == "Not found":
            site_address = address
        legal_desc = find_field('Legal Description')
        year_built = find_field('Year Built')
        
        # Extract square footage
        living_sf = "Not found"
        gross_sf = "Not found"
        for td in soup.find_all('td'):
            text = td.get_text(strip=True)
            if text == 'Living SF':
                next_td = td.find_next_sibling('td')
                living_sf = next_td.get_text(strip=True) if next_td else "Not found"
            elif text == 'Gross SF':
                next_td = td.find_next_sibling('td')
                gross_sf = next_td.get_text(strip=True) if next_td else "Not found"
        
        living_units = find_field('Living Units')
        
        # Extract values from "Final Values" table
        market_value = "Not found"
        assessed_value = "Not found"
        taxable_value = "Not found"
        
        for header in soup.find_all(['h3', 'h4', 'h2']):
            if 'final values' in header.get_text().lower() or 'values' in header.get_text().lower():
                value_table = header.find_next('table')
                if value_table:
                    rows = value_table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 4:
                            first_cell = cells[0].get_text(strip=True)
                            if first_cell.isdigit() and len(first_cell) == 4:  # Year like 2025
                                market_value = cells[1].get_text(strip=True) if len(cells) > 1 else "Not found"
                                assessed_value = cells[2].get_text(strip=True) if len(cells) > 2 else "Not found"
                                taxable_value = cells[3].get_text(strip=True) if len(cells) > 3 else "Not found"
                                break
                if market_value != "Not found":
                    break
        
        # Extract sale history
        last_sale_date = "Not found"
        last_sale_price = "Not found"
        
        for header in soup.find_all(['h3', 'h4', 'h2']):
            if 'sales history' in header.get_text().lower():
                sales_table = header.find_next('table')
                if sales_table:
                    rows = sales_table.find_all('tr')
                    for row in rows[1:]:  # Skip header row
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            date_text = cells[0].get_text(strip=True)
                            if date_text and 'Sale Date' not in date_text:
                                last_sale_date = date_text
                                last_sale_price = cells[1].get_text(strip=True)
                                break
                if last_sale_date != "Not found":
                    break
        
        # Extract lot size
        lot_size = "Not found"
        land_text = soup.find(string=re.compile(r'Land Area:', re.I))
        if land_text:
            match = re.search(r'≅\s*([\d,]+)\s*sf', str(land_text))
            if match:
                lot_size = f"{match.group(1)} sq ft"
        
        tax_district = find_field('Current Tax District')
        flood_zone = find_field('Flood Zone')
        
        # Compile results
        property_data = {
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
            "bedrooms": "N/A",
            "bathrooms": "N/A",
            "livingUnits": living_units,
            "marketValue": market_value,
            "assessedValue": assessed_value,
            "taxableValue": taxable_value,
            "lastSaleDate": last_sale_date,
            "lastSalePrice": last_sale_price,
            "foundation": "N/A",
            "roofType": "N/A",
            "quality": "N/A",
            "taxDistrict": tax_district,
            "floodZone": flood_zone,
            "county": "Pinellas"
        }
        
        print(f"Extraction complete. Owner: {owner}, Parcel: {parcel_id}")
        return property_data
        
    except requests.Timeout:
        return {"error": "Request timed out - county website slow", "status": "error"}
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {"error": f"Scraping error: {str(e)}", "status": "error"}

@app.route('/api/search', methods=['POST'])
def search_property():
    """Main search endpoint"""
    data = request.json
    address = data.get('address')
    county = data.get('county')
    
    if not address or not county:
        return jsonify({"error": "Address and county required"}), 400
    
    print(f"\n=== SEARCH REQUEST ===")
    print(f"Address: {address}")
    print(f"County: {county}")
    
    if county.lower() == 'pinellas':
        result = scrape_pinellas_property(address)
    else:
        result = {"error": f"{county} County not yet supported", "status": "error"}
    
    return jsonify(result)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "running",
        "message": "Property scraper backend is active",
        "version": "2.0",
        "supported_counties": ["Pinellas"]
    })

@app.route('/api/test', methods=['GET'])
def test_scraper():
    """Test with known address"""
    print("\n=== TEST REQUEST ===")
    result = scrape_pinellas_property("1505 MAPLE ST")
    return jsonify(result)

@app.route('/api/debug', methods=['GET'])
def debug_scraper():
    """Debug endpoint - shows raw response from county site"""
    try:
        print("\n=== DEBUG REQUEST ===")
        address = "1505 MAPLE ST"
        base_url = "https://www.pcpao.gov"
        search_url = f"{base_url}/quick-search"
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        params = {
            'qu': '1',
            'input': address,
            'search_option': 'address'
        }
        response = session.get(search_url, params=params, timeout=30)
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        return jsonify({
            "status_code": response.status_code,
            "final_url": response.url,
            "html_preview": response.text[:3000],
            "checks": {
                "has_parcel_number": "Parcel Number" in response.text,
                "has_owner_name": "Owner Name" in response.text,
                "has_property_details_url": "/property-details" in response.url,
                "has_final_values": "Final Values" in response.text or "final values" in response.text.lower(),
                "has_sales_history": "Sales History" in response.text or "sales history" in response.text.lower()
            }
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"})

@app.route('/', methods=['GET'])
def home():
    """Root endpoint"""
    return jsonify({
        "message": "Florida Property Scraper API",
        "version": "2.0",
        "endpoints": {
            "health": "/api/health - Check if API is running",
            "test": "/api/test - Test with sample property",
            "search": "/api/search - Search for property (POST)",
            "debug": "/api/debug - Debug county website response"
        }
    })

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🏠 Florida Property Scraper - Pinellas County v2.0")
    print("="*60)
    print("Ready to scrape property data!")
    print("="*60 + "\n")
    
    app.run(debug=True, port=5000, host='0.0.0.0')
