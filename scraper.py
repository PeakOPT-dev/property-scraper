"""
Florida Property Scraper Backend - Pinellas County (FIXED)
Handles search results page and navigates to property details
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
    Handles both search results and direct property pages
    """
    try:
        base_url = "https://www.pcpao.gov"
        search_url = f"{base_url}/quick-search"
        
        # Clean the address - remove city names that break the search
        # Pinellas County search works with: "1505 MAPLE ST" OR "1505 MAPLE ST 33755"
        # But FAILS with city names like "CLEARWATER"
        city_names = ['CLEARWATER', 'LARGO', 'ST PETERSBURG', 'SAINT PETERSBURG', 
                      'PINELLAS PARK', 'DUNEDIN', 'TARPON SPRINGS', 'SAFETY HARBOR',
                      'SEMINOLE', 'BELLEAIR', 'GULFPORT', 'TREASURE ISLAND', 
                      'ST PETE BEACH', 'MADEIRA BEACH', 'REDINGTON BEACH', 'FL', 'FLORIDA']
        
        clean_address = address.upper()
        for city in city_names:
            # Use word boundaries to avoid partial matches
            clean_address = re.sub(r'\b' + city + r'\b', '', clean_address, flags=re.IGNORECASE)
        
        # Remove commas and extra spaces
        clean_address = clean_address.replace(',', ' ')
        clean_address = ' '.join(clean_address.split())
        
        print(f"Original: {address}")
        print(f"Cleaned: {clean_address}")
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Step 1: Perform search with CLEAN address
        params = {'qu': '1', 'search': clean_address}
        response = session.get(search_url, params=params, timeout=30)
        
        if response.status_code != 200:
            return {"error": "Failed to connect to county website", "status": "error"}
        
        # Check if we landed on a property detail page or search results
        if '/property-details?' in response.url or 'Parcel Summary' in response.text:
            # We're on a property detail page - parse it
            soup = BeautifulSoup(response.content, 'html.parser')
        else:
            # We're on search results - need to find first property link
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for property detail link
            property_link = soup.find('a', href=re.compile(r'/property-details\?'))
            
            if not property_link:
                return {
                    "error": "No property found for this address. Try a more specific search.",
                    "status": "error",
                    "suggestion": "Try format: '1505 MAPLE ST' or include city"
                }
            
            # Navigate to property details page
            detail_url = base_url + property_link['href']
            time.sleep(1)  # Be nice to the server
            response = session.get(detail_url, timeout=30)
            soup = BeautifulSoup(response.content, 'html.parser')
        
        # Now extract data from property details page
        # Extract using table structure
        def find_field_value(label_text):
            """Helper to find value by label in table"""
            for td in soup.find_all('td'):
                if label_text.lower() in td.get_text().lower():
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        return next_td.get_text(strip=True)
            return "Not found"
        
        # Extract Parcel Number
        parcel_id = find_field_value('Parcel Number')
        
        # Extract Owner Name
        owner = find_field_value('Owner Name')
        
        # Extract Property Use
        property_type = find_field_value('Property Use')
        
        # Extract Site Address
        site_address = find_field_value('Site Address')
        if site_address == "Not found":
            site_address = address
        
        # Extract Legal Description
        legal_desc = find_field_value('Legal Description')
        
        # Extract Year Built
        year_built = find_field_value('Year Built')
        
        # Extract Living SF / Gross SF
        living_sf = "Not found"
        gross_sf = "Not found"
        
        # Look for Living SF in the summary section
        for td in soup.find_all('td'):
            text = td.get_text(strip=True)
            if text == 'Living SF':
                next_td = td.find_next_sibling('td')
                if next_td:
                    living_sf = next_td.get_text(strip=True)
            elif text == 'Gross SF':
                next_td = td.find_next_sibling('td')
                if next_td:
                    gross_sf = next_td.get_text(strip=True)
        
        # Extract Living Units
        living_units = find_field_value('Living Units')
        
        # Extract Current Values from table
        market_value = "Not found"
        assessed_value = "Not found"
        taxable_value = "Not found"
        
        # Look for "Final Values" section
        for h3 in soup.find_all(['h3', 'h4']):
            if 'final values' in h3.get_text().lower():
                table = h3.find_next('table')
                if table:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 4 and cells[0].get_text(strip=True) != 'Year':
                            market_value = cells[1].get_text(strip=True) if len(cells) > 1 else "Not found"
                            assessed_value = cells[2].get_text(strip=True) if len(cells) > 2 else "Not found"
                            taxable_value = cells[3].get_text(strip=True) if len(cells) > 3 else "Not found"
                            break
                break
        
        # Extract Last Sale Info from Sales History
        last_sale_date = "Not found"
        last_sale_price = "Not found"
        
        for h3 in soup.find_all(['h3', 'h4']):
            if 'sales history' in h3.get_text().lower():
                table = h3.find_next('table')
                if table:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2 and 'sale date' not in cells[0].get_text().lower():
                            last_sale_date = cells[0].get_text(strip=True)
                            last_sale_price = cells[1].get_text(strip=True)
                            break
                break
        
        # Extract Land Area
        lot_size = "Not found"
        land_area_text = soup.find(string=re.compile(r'Land Area:', re.I))
        if land_area_text:
            match = re.search(r'≅\s*([\d,]+)\s*sf', str(land_area_text))
            if match:
                lot_size = f"{match.group(1)} sq ft"
        
        # Extract Tax District
        tax_district = find_field_value('Current Tax District')
        
        # Extract Flood Zone
        flood_zone = find_field_value('Flood Zone')
        
        # Compile all data
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
        
        return property_data
        
    except requests.Timeout:
        return {
            "error": "Request timed out. County website may be slow or down.",
            "status": "error"
        }
    except Exception as e:
        return {
            "error": f"Scraping error: {str(e)}",
            "status": "error",
            "debug": str(e)
        }

@app.route('/api/search', methods=['POST'])
def search_property():
    """
    API endpoint to search for property
    """
    data = request.json
    address = data.get('address')
    county = data.get('county')
    
    if not address or not county:
        return jsonify({"error": "Address and county required"}), 400
    
    print(f"Searching: {address} in {county} County")
    
    if county.lower() == 'pinellas':
        result = scrape_pinellas_property(address)
    else:
        result = {
            "error": f"{county} County scraper not yet implemented",
            "status": "error"
        }
    
    return jsonify(result)

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    """
    return jsonify({
        "status": "running",
        "message": "Property scraper backend is active",
        "supported_counties": ["Pinellas"]
    })

@app.route('/api/test', methods=['GET'])
def test_scraper():
    """
    Test endpoint with known address
    """
    result = scrape_pinellas_property("1505 MAPLE ST CLEARWATER")
    return jsonify(result)

@app.route('/', methods=['GET'])
def home():
    """
    Root endpoint
    """
    return jsonify({
        "message": "Florida Property Scraper API",
        "endpoints": {
            "health": "/api/health",
            "test": "/api/test",
            "search": "/api/search (POST)"
        }
    })

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🏠 Florida Property Scraper - Pinellas County")
    print("="*60)
    print("Server: http://localhost:5000")
    print("Health: http://localhost:5000/api/health")
    print("Test:   http://localhost:5000/api/test")
    print("="*60 + "\n")
    
    app.run(debug=True, port=5000, host='0.0.0.0')
