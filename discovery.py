import re
import time
import urllib.parse
from typing import List, Dict, Any, Optional
from duckduckgo_search import DDGS
from urllib.parse import urlparse

from settings import settings
from db_manager import get_or_create_lead

# Non-business / foreign TLDs to exclude
EXCLUDED_TLDS = {
    ".in", ".pk", ".sa", ".uk", ".au", ".ca", ".de", ".fr", ".cn", ".jp",
    ".edu", ".gov", ".mil", ".ac.in", ".edu.in", ".gov.in", ".nic.in"
}

# Known aggregate directories, social platforms, news and education portals
EXCLUDED_DOMAINS = {
    "yelp.com", "yellowpages.com", "angi.com", "thumbtack.com", "homeadvisor.com",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "bbb.org",
    "mapquest.com", "tripadvisor.com", "wikipedia.org", "houzz.com", "groupon.com",
    "superpages.com", "manta.com", "dexknows.com", "city-data.com", "zillow.com",
    "realtor.com", "patch.com", "nextdoor.com", "indeed.com", "glassdoor.com",
    "chamberofcommerce.com", "yellowbook.com", "bizapedia.com", "crunchbase.com",
    "apple.com", "google.com", "bing.com", "yahoo.com", "wikihow.com", "investopedia.com",
    "forbes.com", "dictionary.com", "vocabulary.com", "shiksha.com", "collegedunia.com",
    "nobroker.in", "careers360.com", "cardekho.com", "sastaticket.pk", "bookme.pk"
}

def clean_domain(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if ":" in netloc:
            netloc = netloc.split(":")[0]
        return netloc if netloc else None
    except Exception:
        return None

def is_valid_business_website(url: str) -> bool:
    domain = clean_domain(url)
    if not domain or len(domain) < 4:
        return False
        
    # Exclude foreign and academic/gov TLDs
    if any(domain.endswith(tld) for tld in EXCLUDED_TLDS):
        return False
    
    # Exclude directory/social/news domains
    for excluded in EXCLUDED_DOMAINS:
        if domain == excluded or domain.endswith("." + excluded):
            return False
            
    # Exclude file downloads
    if any(url.lower().endswith(ext) for ext in [".pdf", ".jpg", ".png", ".zip", ".docx"]):
        return False
        
    return True

def extract_business_name_from_title(title: str, query_niche: str) -> str:
    """Extracts a clean business name from search result title."""
    parts = re.split(r'[\-\|\:\–\—]', title)
    if parts:
        candidate = parts[0].strip()
        if len(candidate) > 2 and len(candidate) < 60:
            return candidate
    return title.strip()[:60]

def discover_businesses_for_city(city: str, state: str, max_leads_per_niche: int = 4) -> List[Dict[str, Any]]:
    """Discovers local small businesses for a target US city/state using US regional search."""
    discovered_leads = []
    ddgs = DDGS()
    
    print(f"[Discovery] Searching for local US businesses in {city}, {state} (US Region)...", flush=True)
    
    for niche in settings.BUSINESS_NICHES:
        queries = [
            f'"{niche}" "{city}, {state}" local business website',
            f'best "{niche}" "{city}" "{state}"'
        ]
        
        for query in queries:
            try:
                # Force US region
                results = list(ddgs.text(query, region="us-en", max_results=max_leads_per_niche + 3))
                time.sleep(0.6)
                
                for r in results:
                    url = r.get("href", "")
                    title = r.get("title", "")
                    
                    if not is_valid_business_website(url):
                        continue
                        
                    domain = clean_domain(url)
                    if not domain:
                        continue
                        
                    biz_name = extract_business_name_from_title(title, niche)
                    parsed = urlparse(url)
                    clean_root_url = f"{parsed.scheme}://{parsed.netloc}"
                    
                    lead_obj, is_new = get_or_create_lead(
                        business_name=biz_name,
                        website_url=clean_root_url,
                        domain=domain,
                        city=city,
                        state=state,
                        niche=niche
                    )
                    
                    if is_new:
                        print(f"  [+] Discovered new business: {biz_name} ({domain}) - {niche}", flush=True)
                        discovered_leads.append({
                            "id": lead_obj.id,
                            "business_name": biz_name,
                            "website_url": clean_root_url,
                            "domain": domain,
                            "city": city,
                            "state": state,
                            "niche": niche
                        })
            except Exception as e:
                time.sleep(1.0)
                
    print(f"[Discovery] Total new leads found for {city}, {state}: {len(discovered_leads)}", flush=True)
    return discovered_leads
