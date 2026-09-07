import re
import requests
from bs4 import BeautifulSoup
from typing import List, Set, Optional
from urllib.parse import urljoin, urlparse

from db_manager import add_contact_email

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Email regex pattern
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', re.IGNORECASE)

# Ignored email stems and domains (generic junk/templates)
JUNK_EMAILS = {
    "example@example.com", "user@domain.com", "email@example.com", "info@example.com",
    "name@domain.com", "yourname@domain.com", "test@test.com", "support@wix.com",
    "abuse@godaddy.com", "privacy@squarespace.com", "contact@wixpress.com"
}

JUNK_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js"}

def is_valid_contact_email(email: str, domain: str) -> bool:
    email = email.strip().lower()
    if not email or "@" not in email:
        return False
        
    if email in JUNK_EMAILS:
        return False
        
    # Check for image or script filename mistaken as email
    if any(email.endswith(ext) for ext in JUNK_EXTENSIONS):
        return False
        
    parts = email.split("@")
    if len(parts) != 2:
        return False
        
    user, host = parts
    if len(user) < 1 or len(host) < 4:
        return False
        
    # Check if host contains invalid characters or numbers only
    if not re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', host):
        return False
        
    return True

def extract_emails_from_html(html_content: str, base_url: str) -> Set[str]:
    found_emails = set()
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 1. Look for mailto links
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            raw_email = href.split(":", 1)[1].split("?")[0].strip()
            if raw_email:
                found_emails.add(raw_email.lower())
                
    # 2. Text regex search
    text = soup.get_text(separator=" ")
    matches = EMAIL_REGEX.findall(text)
    for m in matches:
        found_emails.add(m.lower())
        
    # 3. Handle obfuscated emails (e.g. info [at] domain [dot] com)
    obfuscated = re.findall(r'([a-zA-Z0-9._%+-]+)\s*(?:\[at\]|\(at\)|@)\s*([a-zA-Z0-9.-]+)\s*(?:\[dot\]|\(dot\)|\.)\s*([a-zA-Z]{2,})', text, re.IGNORECASE)
    for user, d_part, tld in obfuscated:
        found_emails.add(f"{user}@{d_part}.{tld}".lower())
        
    return found_emails

def harvest_contact_emails(lead_id: int, website_url: str, domain: str) -> List[str]:
    """Crawls homepage and key contact subpages to extract legitimate contact emails."""
    headers = {"User-Agent": USER_AGENT}
    discovered_valid_emails = set()
    
    pages_to_check = [
        website_url,
        urljoin(website_url, "/contact"),
        urljoin(website_url, "/contact-us"),
        urljoin(website_url, "/contact_us"),
        urljoin(website_url, "/about"),
        urljoin(website_url, "/about-us"),
        urljoin(website_url, "/reach-us"),
        urljoin(website_url, "/our-team")
    ]
    
    visited_urls = set()
    
    for page_url in pages_to_check:
        if page_url in visited_urls:
            continue
        visited_urls.add(page_url)
        
        try:
            resp = requests.get(page_url, headers=headers, timeout=8, allow_redirects=True)
            if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
                raw_emails = extract_emails_from_html(resp.text, page_url)
                for email in raw_emails:
                    if is_valid_contact_email(email, domain):
                        discovered_valid_emails.add((email, page_url))
        except Exception:
            continue
            
        # If we already found 2 verified contact emails, no need to crawl all other subpages
        if len(discovered_valid_emails) >= 2:
            break
            
    saved_emails = []
    for email, src in discovered_valid_emails:
        added = add_contact_email(lead_id, email, source_page=src)
        saved_emails.append(email)
        print(f"  [@] Found contact email for Lead #{lead_id}: {email}")
        
    return saved_emails
