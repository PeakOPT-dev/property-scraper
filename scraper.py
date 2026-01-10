"""
Florida Property Scraper Backend - Pinellas County
Download this file as scraper.py and deploy to PythonAnywhere
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
CORS(app)

def scrape_pinellas_property(address):
    """
    Scrapes Pinellas County Property Appraiser for property details
    """
    try:
        base_url = "https://www.pcpao.gov"
        search_url = f"{base_url}/quick-search"
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        params = {'qu': '1', 'search': address}
        response = session.get(search_url, params=params, timeout=15)
        
        if response.status_code != 200:
            return {"error": "Failed to connect to county website", "status": "error"}
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract Parcel Number
        parcel_elem = soup.find('td', string=re.compile('Parcel Number', re.I))
        parcel_id = parcel_elem.find_next_sibling('td').text.strip() if parcel_elem else "Not found"
        
        # Extract Owner Name
        owner_elem = soup.find('td', string=re.compile('Owner Name', re.I))
        owner = owner_elem.find_next_sibling('td').text.strip() if owner_elem else "Not found"
        
        # Extract Property Use
        use_elem = soup.find('td', string=re.compile('Property Use', re.I))
        property_type = use_elem.find_next_sibling('td').text.strip() if use_elem else "Not found"
        
        # Extract Site Address
        site_elem = soup.find('td', string=re.compile('Site Address', re.I))
        site_address = address
        if site_elem:
            addr_td = site_elem.find_next_sibling('td')
            if addr_td:
                site_address = ' '.join(addr_td.stripped_strings)
        
        # Extract Legal Description
        legal_elem = soup.find('td', string=re.compile('Legal Description', re.I))
        legal_desc = legal_elem.find_next_sibling('td').text.strip() if legal_elem else "Not found"
        
        # Extract Year Built
        year_elem = soup.find('td', string=re.compile('Year Built', re.I))
        year_built = year_elem.find_next_sibling('td').text.strip() if year_elem else "Not found"
        
        # Extract Living SF / Gross SF
        living_sf = "Not found"
        gross_sf = "Not found"
        sf_elems = soup.find_all('td', string=re.compile('Living SF|Gross SF', re.I))
        for elem in sf_elems:
            label = elem.text.strip()
            value = elem.find_next_sibling('td')
            if value:
                if 'Living SF' in label:
                    living_sf = value.text.strip()
                elif 'Gross SF' in label:
                    gross_sf = value.text.strip()
        
        # Extract Living Units
        units_elem = soup.find('td', string=re.compile('Living Units', re.I))
        living_units = units_elem.find_next_sibling('td').text.strip() if units_elem else "Not found"
        
        # Extract Current Values
        market_value = "Not found"
        assessed_value = "Not found"
        taxable_value = "Not found"
        
        value_header = soup.find('h3', string=re.compile('Final Values', re.I))
        if value_header:
            value_table = value_header.find_next('table')
            if value_table:
                rows = value_table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 3 and 'Year' not in cells[0].text:
                        market_value = cells[1].text.strip() if len(cells) > 1 else "Not found"
                        assessed_value = cells[2].text.strip() if len(cells) > 2 else "Not found"
                        taxable_value = cells[3].text.strip() if len(cells) > 3 else "Not found"
                        break
        
        # Extract Last Sale Info
        last_sale_date = "Not found"
        last_sale_price = "Not found"
        
        sales_header = soup.find('h3', string=re.compile('Sales History', re.I))
        if sales_header:
            sales_table = sales_header.find_next('table')
            if sales_table:
                rows = sales_table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2 and 'Sale Date' not in cells[0].text:
                        last_sale_date = cells[0].text.strip()
                        last_sale_price = cells[1].text.strip()
                        break
        
        # Extract Land Area
        lot_size = "Not found"
        land_text = soup.find(string=re.compile('Land Area:', re.I))
        if land_text:
            match = re.search(r'≅\s*([\d,]+)\s*sf', str(land_text))
            if match:
                lot_size = f"{match.group(1)} sq ft"
        
        # Extract Structural Details
        foundation = "Not found"
        roof_type = "Not found"
        quality = "Not found"
        
        struct_header = soup.find('h3', string=re.compile('Structural Elements', re.I))
        if struct_header:
            struct_div = struct_header.find_next('div')
            if struct_div:
                found_elem = struct_div.find(string=re.compile('Foundation:', re.I))
                if found_elem:
                    foundation = found_elem.parent.next_sibling.strip() if found_elem.parent.next_sibling else "Not found"
                
                roof_elem = struct_div.find(string=re.compile('Roof Cover:', re.I))
                if roof_elem:
                    roof_type = roof_elem.parent.next_sibling.strip() if roof_elem.parent.next_sibling else "Not found"
                
                qual_elem = struct_div.find(string=re.compile('Quality:', re.I))
                if qual_elem:
                    quality = qual_elem.parent.next_sibling.strip() if qual_elem.parent.next_sibling else "Not found"
        
        # Extract Tax District
        district_elem = soup.find('td', string=re.compile('Current Tax District', re.I))
        tax_district = district_elem.find_next_sibling('td').text.strip() if district_elem else "Not found"
        
        # Extract Flood Zone
        flood_elem = soup.find('td', string=re.compile('Flood Zone', re.I))
        flood_zone = "Not found"
        if flood_elem:
            flood_td = flood_elem.find_next_sibling('td')
            if flood_td:
                flood_link = flood_td.find('a')
                flood_zone = flood_link.text.strip() if flood_link else flood_td.text.strip()
        
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
            "foundation": foundation,
            "roofType": roof_type,
            "quality": quality,
            "taxDistrict": tax_district,
            "floodZone": flood_zone,
            "county": "Pinellas"
        }
        
        return property_data
        
    except Exception as e:
        return {
            "error": f"Scraping error: {str(e)}",
            "status": "error"
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

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🏠 Florida Property Scraper - Pinellas County")
    print("="*60)
    print("Server: http://localhost:5000")
    print("Health: http://localhost:5000/api/health")
    print("Test:   http://localhost:5000/api/test")
    print("="*60 + "\n")
    
    app.run(debug=True, port=5000, host='0.0.0.0')
