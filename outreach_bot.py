import os
import json
from datetime import datetime
import random
import time
import google.generativeai as genai
from google.oauth2.service_account import Credentials
import gspread
import requests


# DEBUG: Check if environment variables exist
print("=" * 50)
print("DEBUG: Checking environment variables...")
print(f"GEMINI_API_KEY exists: {'GEMINI_API_KEY' in os.environ}")
print(f"SENDGRID_API_KEY exists: {'SENDGRID_API_KEY' in os.environ}")
print(f"GOOGLE_SHEET_ID exists: {'GOOGLE_SHEET_ID' in os.environ}")
print(f"GOOGLE_CREDS exists: {'GOOGLE_CREDS' in os.environ}")

if 'GOOGLE_CREDS' in os.environ:
    creds_sample = os.environ['GOOGLE_CREDS'][:50]  # First 50 chars
    print(f"GOOGLE_CREDS starts with: {creds_sample}")
    print(f"GOOGLE_CREDS length: {len(os.environ['GOOGLE_CREDS'])}")
else:
    print("WARNING: GOOGLE_CREDS is completely missing!")

print("=" * 50)
print()

def validate_google_creds():
    """Validate that GOOGLE_CREDS is valid JSON"""
    print("=" * 50)
    print("DEBUG: Validating GOOGLE_CREDS JSON...")
    
    if not GOOGLE_CREDS:
        print("✗ GOOGLE_CREDS is empty or None")
        return False
    
    try:
        creds_dict = json.loads(GOOGLE_CREDS)
        print(f"✓ JSON parsed successfully")
        print(f"  Keys in JSON: {list(creds_dict.keys())}")
        print(f"  Service account email: {creds_dict.get('client_email', 'NOT FOUND')}")
        print(f"  Project ID: {creds_dict.get('project_id', 'NOT FOUND')}")
        return True
    except json.JSONDecodeError as e:
        print(f"✗ JSON parsing failed: {e}")
        print(f"  First 100 chars: {GOOGLE_CREDS[:100]}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

# ============ CONFIGURATION ============
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")

SENDGRID_FROM_EMAIL = "your-verified-email@example.com"  # Change this!
MAX_EMAILS_PER_RUN = 5

# ============ SETUP APIs ============
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

def get_google_sheet():
    """Connect to Google Sheet with detailed debugging"""
    print("  Starting Google Sheet connection...")
    
    try:
        print("  Step 1: Parsing JSON credentials...")
        creds_dict = json.loads(GOOGLE_CREDS)
        print("    ✓ JSON parsed")
        
        print("  Step 2: Creating Credentials object...")
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        print("    ✓ Credentials created")
        
        print("  Step 3: Authorizing with gspread...")
        client = gspread.authorize(creds)
        print("    ✓ gspread authorized")
        
        print(f"  Step 4: Opening sheet with ID: {GOOGLE_SHEET_ID}")
        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        print(f"    ✓ Sheet opened: {sheet.title}")
        
        print("  Step 5: Getting first worksheet...")
        worksheet = sheet.sheet1
        print(f"    ✓ Worksheet accessed: {worksheet.title}")
        
        return worksheet
        
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parsing failed: {e}")
        return None
    except Exception as e:
        print(f"  ✗ Error at some step: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()  # This prints the full error stack
        return None

# ============ MOCK LEADS (for testing) ============
def get_test_leads():
    """Return sample leads for testing"""
    return [
        {
            "name": "João Silva",
            "business_name": "Silva Adventure Tours",
            "email": "joao@silvaadventure.com",
            "source": "google_maps",
            "reviews_mention": "Great hiking tours, knows Fanal Forest well"
        },
        {
            "name": "Maria Costa",
            "business_name": "Madeira Nature Walks",
            "email": "maria@madeiranaturewalks.pt",
            "source": "google_maps",
            "reviews_mention": "Expert guide, takes groups to Fanal regularly"
        },
        {
            "name": "Pedro Nunes",
            "business_name": "Fanal Forest Expeditions",
            "email": "pedro@fanalexpeditions.com",
            "source": "google_maps",
            "reviews_mention": "Specializes in Fanal Forest tours"
        }
    ]

# ============ PERSONALIZATION WITH GEMINI ============
def personalize_message(lead):
    """Use Gemini to personalize outreach message"""
    
    prompt = f"""
You are helping reach out to a tour guide in Madeira. Here's their information:
- Name: {lead.get('name', 'Guide')}
- Business: {lead.get('business_name', 'Unknown')}
- Reviews mention: {lead.get('reviews_mention', '')}

Write a SHORT, friendly, personalized email (2-3 paragraphs max) asking them to mention the Herdy app to their clients who visit Fanal Forest.

The Herdy app helps hikers find wildlife/livestock on trails in real-time using crowdsourced data. It's completely free with no commission model.

Keep it casual and genuine. Mention their business/tours specifically. End with a question asking if they'd be open to chatting.

Write ONLY the email body, no subject line, no preamble. Keep it under 200 words.
"""
    
    try:
        print(f"  ⏳ Personalizing message with Gemini...")
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"  ✗ Error personalizing: {e}")
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
    
    subject = f"Free Tool for Your {lead.get('business_name', 'Tours')} Guests - Herdy App"
    
    data = {
        "personalizations": [{"to": [{"email": email, "name": lead.get("name", "")}]}],
        "from": {"email": SENDGRID_FROM_EMAIL, "name": "Gabriel - Herdy"},
        "subject": subject,
        "content": [{"type": "text/plain", "value": message_body}]
    }
    
    try:
        print(f"  📧 Sending email to {email}...")
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code in [200, 201, 202]:
            return True, "sent"
        else:
            print(f"  ✗ SendGrid error: {response.status_code}")
            print(f"  Response: {response.text}")
            return False, f"SendGrid error: {response.status_code}"
    except Exception as e:
        print(f"  ✗ Error sending email: {e}")
        return False, str(e)

# ============ TRACKING ============
def log_to_sheet(worksheet, lead, message, status, response_text=""):
    """Log outreach to Google Sheet"""
    if not worksheet:
        print("  ✗ No worksheet to log to")
        return
    
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
        print(f"  ✓ Logged to sheet")
    except Exception as e:
        print(f"  ✗ Error logging to sheet: {e}")

# ============ MAIN EXECUTION ============
def main():
    print("🤖 Starting Herdy Outreach Bot...")
    print()

    # Validate creds first
    if not validate_google_creds():
        print("✗ Cannot proceed - invalid credentials")
        return
    
    # Get Google Sheet
    worksheet = get_google_sheet()
    if not worksheet:
        print("✗ Cannot proceed without Google Sheet access")
        return
    
    print("✓ Connected to Google Sheet")
    print()
    
    # Get leads (test data for now)
    print("📋 Loading leads...")
    leads = get_test_leads()
    print(f"✓ Loaded {len(leads)} test leads")
    print()
    
    # Process leads
    emails_sent = 0
    for i, lead in enumerate(leads[:MAX_EMAILS_PER_RUN], 1):
        print(f"[{i}/{len(leads)}] Processing: {lead.get('name', 'Unknown')}")
        
        # Personalize message
        message = personalize_message(lead)
        if not message:
            print(f"  ✗ Failed to personalize")
            log_to_sheet(worksheet, lead, "", "failed_personalization")
            continue
        
        # Send email
        success, status = send_email(lead, message)
        if success:
            print(f"  ✓ Email sent successfully")
            log_to_sheet(worksheet, lead, message, "sent")
            emails_sent += 1
        else:
            print(f"  ✗ Failed to send: {status}")
            log_to_sheet(worksheet, lead, message, "failed", status)
        
        print()
        # Rate limit
        time.sleep(random.uniform(1, 2))
    
    print("=" * 50)
    print(f"✓ Bot completed successfully!")
    print(f"✓ Emails sent: {emails_sent}/{len(leads)}")
    print("=" * 50)

if __name__ == "__main__":
    main()
