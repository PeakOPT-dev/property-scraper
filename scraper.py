from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import re
import os

app = Flask(__name__)
CORS(app)

# --- 1. HEALTH ROUTE (Bring this back so logs aren't red) ---
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "active", "platform": "Render Free Tier"})

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Property Scraper API is Running"})

# --- 2. OPTIMIZED SCRAPER ---
def scrape_pinellas_property(address):
    print(f"Starting scrape for: {address}")
    
    # Clean Address Logic
    city_names = ['CLEARWATER', 'LARGO', 'ST PETERSBURG', 'SAINT PETERSBURG', 
                  'PINELLAS PARK', 'DUNEDIN', 'TARPON SPRINGS', 'SAFETY HARBOR', 'FL', 'FLORIDA']
    clean_address = address.upper()
    for city in city_names:
        clean_address = re.sub(r'\b' + city + r'\b', '', clean_address, flags=re.IGNORECASE)
    clean_address = ' '.join(clean_address.replace(',', ' ').split())

    try:
        with sync_playwright() as p:
            # --- MEMORY OPTIMIZATION FLAGS ---
            # These are CRITICAL for running on Render Free Tier
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage', # Uses disk instead of RAM for shared mem
                    '--disable-gpu',           # Saves memory
                    '--single-process'         # strictly for low-resource envs
                ]
            )
            
            # Create context with blocked resources to save data/time
            context = browser.new_context()
            # Block images and fonts to save bandwidth/memory
            context.route("**/*", lambda route: route.abort() 
                          if route.request.resource_type in ["image", "font", "media"] 
                          else route.continue_())

            page = context.new_page()
            
            # Go to search
            base_url = "https://www.pcpao.gov/quick-search"
            final_url = f"{base_url}?qu=1&input={clean_address}&search_option=address"
            print(f"Navigating to: {final_url}")
            
            # Lower timeout to fail fast if stuck
            page.goto(final_url, timeout=30000)

            # Wait for results
            try:
                page.wait_for_selector("table, text='Parcel Number'", timeout=15000)
            except:
                print("Selector timeout - continuing to parse whatever loaded.")

            html_content = page.content()
            browser.close()
            
            # Parse (Standard Logic)
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Simple fallback extraction
            parcel_id = "Not found"
            if soup.find(string=re.compile("Parcel Number")):
                parcel_id = "Found (Check details)" 
            
            # Attempt to grab values from the first row of any table (Quick extraction)
            # You can paste your detailed logic here, but keeping it light for testing
            
            return {
                "status": "success",
                "address": address,
                "parcelId": parcel_id,
                "county": "Pinellas",
                "note": "Scraped via Render Free Tier"
            }

    except Exception as e:
        print(f"CRASH: {str(e)}")
        return {"error": str(e), "status": "error"}

@app.route('/api/search', methods=['POST'])
def search_property():
    data = request.json
    return jsonify(scrape_pinellas_property(data.get('address', '')))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
