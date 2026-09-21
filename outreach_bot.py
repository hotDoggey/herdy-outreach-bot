import os
import json
from datetime import datetime
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from google.oauth2.service_account import Credentials
import gspread
import requests
import re

# ============ CONFIGURATION ============
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")

# ============ SETUP ============
def get_google_sheet():
    """Connect to Google Sheet"""
    try:
        creds_dict = json.loads(GOOGLE_CREDS)
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        return sheet.sheet1
    except Exception as e:
        print(f"✗ Error connecting to Google Sheet: {e}")
        return None

# ============ SCRAPING ============
def scrape_google_maps_guides():
    """Scrape Fanal Forest tour guides from Google Maps"""
    leads = []
    
    try:
        print("🔍 Scraping Google Maps...")
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0")
        
        driver = webdriver.Chrome(options=options)
        
        # Search for Fanal Forest tours
        search_url = "https://www.google.com/maps/search/fanal+forest+madeira+tours"
        driver.get(search_url)
        time.sleep(5)
        
        # Try to get business listings
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "hfpxzc"))
            )
        except:
            print("  ℹ No results with expected selectors, trying alternative...")
        
        # Get all business links
        businesses = driver.find_elements(By.CLASS_NAME, "hfpxzc")
        
        print(f"  Found {len(businesses)} listings")
        
        for i, business in enumerate(businesses[:10]):  # Limit to 10 per run
            try:
                name = business.get_attribute("aria-label")
                if name:
                    # Extract name and location
                    parts = name.split(",")
                    business_name = parts[0].strip() if parts else name
                    location = ",".join(parts[1:]).strip() if len(parts) > 1 else ""
                    
                    lead = {
                        "name": business_name.split("-")[0].strip() if "-" in business_name else business_name,
                        "business_name": business_name,
                        "location": location,
                        "source": "google_maps",
                        "website": None,
                        "instagram": None,
                        "whatsapp": None
                    }
                    leads.append(lead)
                    print(f"  ✓ {business_name}")
            except Exception as e:
                print(f"  ✗ Error processing listing: {e}")
                continue
        
        driver.quit()
        
    except Exception as e:
        print(f"✗ Google Maps scraping error: {e}")
        try:
            driver.quit()
        except:
            pass
    
    return leads

def extract_contact_info(lead):
    """Try to extract Instagram, WhatsApp from website or common patterns"""
    
    # Try to find Instagram handle (common: instagram.com/username)
    instagram_patterns = [
        r"instagram\.com/([a-zA-Z0-9_\.]+)",
        r"@([a-zA-Z0-9_\.]+)",  # @username format
    ]
    
    # Try to find WhatsApp (common: wa.me/number or direct number)
    whatsapp_patterns = [
        r"wa\.me/(\d{10,15})",
        r"whatsapp\.com/\?phone=(\d{10,15})",
        r"\+?(\d{10,15})",  # Any long number
    ]
    
    # If they have a website, try to scrape it
    if lead.get("website"):
        try:
            response = requests.get(lead["website"], timeout=5)
            text = response.text.lower()
            
            # Find Instagram
            for pattern in instagram_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    lead["instagram"] = match.group(1)
                    break
            
            # Find WhatsApp
            for pattern in whatsapp_patterns:
                match = re.search(pattern, text)
                if match:
                    lead["whatsapp"] = match.group(1)
                    break
        except:
            pass
    
    return lead

# ============ LOGGING ============
def log_to_sheet(worksheet, lead):
    """Log lead to Google Sheet"""
    if not worksheet:
        return
    
    try:
        row = [
            datetime.now().isoformat(),
            lead.get("name", ""),
            lead.get("business_name", ""),
            lead.get("location", ""),
            lead.get("instagram", ""),
            lead.get("whatsapp", ""),
            lead.get("website", ""),
            lead.get("source", ""),
            "na",  # status - you'll fill this in manually
            ""    # notes
        ]
        worksheet.append_row(row)
        return True
    except Exception as e:
        print(f"  ✗ Error logging to sheet: {e}")
        return False

# ============ CHECK FOR DUPLICATES ============
def is_duplicate(worksheet, business_name):
    """Check if this lead already exists in the sheet"""
    try:
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:  # Only headers
            return False
        
        for row in all_values[1:]:
            if row and row[2].lower() == business_name.lower():
                return True
        return False
    except:
        return False

# ============ MAIN EXECUTION ============
def main():
    print("=" * 50)
    print("🤖 Herdy Lead Scout - Manual Mode")
    print("=" * 50)
    print()
    
    # Connect to sheet
    worksheet = get_google_sheet()
    if not worksheet:
        print("✗ Cannot proceed without Google Sheet access")
        return
    
    print("✓ Connected to Google Sheet")
    print()
    
    # Scrape leads
    all_leads = scrape_google_maps_guides()
    
    if not all_leads:
        print("✗ No leads found")
        return
    
    print()
    
    # Filter duplicates and log
    new_leads = 0
    for lead in all_leads:
        if is_duplicate(worksheet, lead["business_name"]):
            print(f"⊘ Already exists: {lead['business_name']}")
            continue
        
        print(f"📝 Adding: {lead['business_name']}")
        
        # Try to extract contact info
        lead = extract_contact_info(lead)
        
        # Log to sheet
        if log_to_sheet(worksheet, lead):
            print(f"  ✓ Logged to sheet")
            new_leads += 1
        
        time.sleep(1)
    
    print()
    print("=" * 50)
    print(f"✓ Scan complete!")
    print(f"✓ New leads found: {new_leads}")
    print("=" * 50)
    print()
    print("📱 Next steps: Check your sheet and manually message on Instagram/WhatsApp")

if __name__ == "__main__":
    main()
