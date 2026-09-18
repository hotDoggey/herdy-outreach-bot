import os
import json
from datetime import datetime
import random
import time
import google.generativeai as genai
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
import gspread
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ============ CONFIGURATION ============
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")  # JSON string

SENDGRID_FROM_EMAIL = "your-verified-email@example.com"  # Change this to your SendGrid verified email
MAX_EMAILS_PER_RUN = 10  # Conservative for testing
FANAL_KEYWORDS = ["fanal", "hiking", "forest", "madeira", "tour guide", "guide"]

# ============ SETUP APIs ============
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

def get_google_sheet():
    """Connect to Google Sheet"""
    creds_dict = json.loads(GOOGLE_CREDS)
    creds = Credentials.from_service_account_info(creds_dict)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID)
    return sheet.worksheet(0)  # First sheet

# ============ LEAD SCRAPING ============
def scrape_google_maps_guides():
    """Scrape tour guides from Google Maps for Fanal Forest"""
    leads = []
    
    try:
        # Using Selenium to scrape Google Maps
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        driver = webdriver.Chrome(options=options)
        
        # Search for Fanal Forest tours on Google Maps
        search_url = "https://www.google.com/maps/search/fanal+forest+madeira+tours"
        driver.get(search_url)
        
        # Wait for results to load
        time.sleep(3)
        
        # Get business listings
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "hfpxzc"))
            )
        except:
            pass
        
        # Extract business info
        businesses = driver.find_elements(By.CLASS_NAME, "hfpxzc")
        
        for business in businesses[:15]:  # Limit to 15 per run
            try:
                name = business.get_attribute("aria-label")
                if name:
                    leads.append({
                        "name": name.split(",")[0],  # Usually format: "Name, Address"
                        "business_name": name.split(",")[0],
                        "source": "google_maps",
                        "website": None,
                        "email": None,
                        "phone": None
                    })
            except:
                continue
        
        driver.quit()
        
    except Exception as e:
        print(f"Error scraping Google Maps: {e}")
    
    return leads

def find_contact_info(lead):
    """Try to find email/phone from their website or social"""
    # This is a simplified version - you can expand it
    
    # Try common email patterns
    if "email" in lead.get("website", "").lower():
        try:
            # Simple regex to find emails in website text
            import re
            response = requests.get(lead["website"], timeout=5)
            emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', response.text)
            if emails:
                lead["email"] = emails[0]
        except:
            pass
    
    # Try common patterns
    if not lead.get("email") and lead.get("website"):
        domain = lead["website"].replace("https://", "").replace("http://", "").split("/")[0]
        patterns = [
            f"info@{domain}",
            f"contact@{domain}",
            f"hello@{domain}"
        ]
        lead["email_variants"] = patterns
    
    return lead

# ============ PERSONALIZATION WITH GEMINI ============
def personalize_message(lead):
    """Use Gemini to personalize outreach message"""
    
    prompt = f"""
You are helping me reach out to a tour guide in Madeira. Here's their information:
- Name: {lead.get('name', 'Guide')}
- Business: {lead.get('business_name', 'Unknown')}
- Source: {lead.get('source', 'Google Maps')}

Write a SHORT, friendly, personalized email (2-3 paragraphs max) asking them to mention the Herdy app to their clients who visit Fanal Forest.

The Herdy app helps hikers find wildlife/livestock on trails in real-time. It's free and no commission model.

Keep it casual and genuine. Mention their business specifically if possible. End with a question asking if they'd be open to a quick chat.

Write ONLY the email body, no subject line, no preamble.
"""
    
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error personalizing with Gemini: {e}")
        return None

# ============ EMAIL SENDING ============
def send_email(lead, message_body):
    """Send email via SendGrid"""
    
    email = lead.get("email")
    if not email:
        return False, "No email found"
    
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }
    
    subject = f"Herdy App - Free Tool for Your {lead.get('business_name', 'Tours')} Guests"
    
    data = {
        "personalizations": [{"to": [{"email": email, "name": lead.get("name", "")}]}],
        "from": {"email": SENDGRID_FROM_EMAIL, "name": "Gabriel - Herdy"},
        "subject": subject,
        "content": [{"type": "text/plain", "value": message_body}]
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code in [200, 201, 202]:
            return True, "Sent"
        else:
            return False, f"SendGrid error: {response.status_code}"
    except Exception as e:
        return False, str(e)

# ============ TRACKING ============
def log_to_sheet(worksheet, lead, message, status, response_text=""):
    """Log outreach to Google Sheet"""
    try:
        row = [
            datetime.now().isoformat(),
            lead.get("name", ""),
            lead.get("email", ""),
            lead.get("business_name", ""),
            lead.get("source", ""),
            message[:100] if message else "",  # First 100 chars
            status,
            response_text,
            ""  # follow_up_date
        ]
        worksheet.append_row(row)
    except Exception as e:
        print(f"Error logging to sheet: {e}")

# ============ MAIN EXECUTION ============
def main():
    print("🤖 Starting Herdy Outreach Bot...")
    
    # Get Google Sheet
    try:
        worksheet = get_google_sheet()
        print("✓ Connected to Google Sheet")
    except Exception as e:
        print(f"✗ Error connecting to Google Sheet: {e}")
        return
    
    # Scrape leads
    print("🔍 Scraping leads from Google Maps...")
    leads = scrape_google_maps_guides()
    print(f"✓ Found {len(leads)} leads")
    
    if not leads:
        print("No leads found. Exiting.")
        return
    
    # Process leads
    emails_sent = 0
    for lead in leads[:MAX_EMAILS_PER_RUN]:
        print(f"\nProcessing: {lead.get('name', 'Unknown')}")
        
        # Find contact info
        lead = find_contact_info(lead)
        
        if not lead.get("email"):
            print(f"  ✗ No email found. Skipping.")
            log_to_sheet(worksheet, lead, "", "no_email")
            continue
        
        # Personalize message
        message = personalize_message(lead)
        if not message:
            print(f"  ✗ Failed to personalize. Skipping.")
            continue
        
        # Send email
        success, status = send_email(lead, message)
        if success:
            print(f"  ✓ Email sent to {lead.get('email')}")
            log_to_sheet(worksheet, lead, message, "sent")
            emails_sent += 1
        else:
            print(f"  ✗ Failed to send: {status}")
            log_to_sheet(worksheet, lead, message, "failed", status)
        
        # Rate limit (be nice to APIs)
        time.sleep(random.uniform(2, 4))
    
    print(f"\n✓ Bot completed. Emails sent: {emails_sent}")

if __name__ == "__main__":
    main()
