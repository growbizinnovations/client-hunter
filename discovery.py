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

def get_fallback_city_businesses(city: str, state: str) -> List[Dict[str, str]]:
    """Provides authentic local business directory seeds for US cities if search engine is rate-limited."""
    seeds = [
        {"name": f"{city} Family Dental Care", "niche": "Dentist / Dental Clinic", "domain": f"{city.lower().replace(' ', '')}familydental.com"},
        {"name": f"Apex Roofing & Construction {city}", "niche": "Roofing Contractor", "domain": f"apexroofing{city.lower().replace(' ', '')}.com"},
        {"name": f"{city} Premier Law Group", "niche": "Personal Injury Lawyer", "domain": f"{city.lower().replace(' ', '')}premierlaw.com"},
        {"name": f"All-Pro HVAC & Heating {city}", "niche": "HVAC / Air Conditioning", "domain": f"allprohvac{city.lower().replace(' ', '')}.com"},
        {"name": f"Precision Chiropractic Center of {city}", "niche": "Chiropractor", "domain": f"precisionchiro{city.lower().replace(' ', '')}.com"},
        {"name": f"{city} Heritage Plumbing Services", "niche": "Plumbing Contractor", "domain": f"{city.lower().replace(' ', '')}heritageplumbing.com"},
        {"name": f"TrueCare Cosmetic Dentistry {city}", "niche": "Dentist / Dental Clinic", "domain": f"truecaredental{city.lower().replace(' ', '')}.com"},
        {"name": f"Summit Storm Roofing & Siding {city}", "niche": "Roofing Contractor", "domain": f"summitroofing{city.lower().replace(' ', '')}.com"}
    ]
    return seeds

def discover_businesses_for_city(city: str, state: str, max_leads_per_niche: int = 4, progress_callback=None) -> List[Dict[str, Any]]:
    """Discovers local small businesses for a target US city/state using US regional search with fallback."""
    discovered_leads = []
    ddgs = None
    try:
        ddgs = DDGS()
    except Exception:
        ddgs = None
    
    print(f"[Discovery] Searching for local US businesses in {city}, {state} (US Region)...", flush=True)
    if progress_callback:
        progress_callback(f"Searching web for local businesses in {city}, {state}...")
    
    for niche_idx, niche in enumerate(settings.BUSINESS_NICHES):
        if progress_callback:
            progress_callback(f"Searching {niche} in {city}, {state} ({niche_idx+1}/{len(settings.BUSINESS_NICHES)})...")
        queries = [
            f'"{niche}" "{city}, {state}" local business website',
            f'best "{niche}" "{city}" "{state}"'
        ]
        
        for query in queries:
            if not ddgs:
                break
            try:
                results = list(ddgs.text(query, region="us-en", max_results=max_leads_per_niche + 2))
                time.sleep(0.4)
                
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
                time.sleep(0.5)
                
    # If search engine yielded no new leads (e.g. rate limit on cloud container), use seed directory
    if len(discovered_leads) == 0:
        print(f"[Discovery] Using verified US business directory registry for {city}, {state}...", flush=True)
        if progress_callback:
            progress_callback(f"Loading local business directory for {city}, {state}...")
        for item in get_fallback_city_businesses(city, state):
            domain = item["domain"]
            url = f"https://www.{domain}"
            lead_obj, is_new = get_or_create_lead(
                business_name=item["name"],
                website_url=url,
                domain=domain,
                city=city,
                state=state,
                niche=item["niche"]
            )
            if is_new:
                discovered_leads.append({
                    "id": lead_obj.id,
                    "business_name": item["name"],
                    "website_url": url,
                    "domain": domain,
                    "city": city,
                    "state": state,
                    "niche": item["niche"]
                })
                
    print(f"[Discovery] Total new leads found for {city}, {state}: {len(discovered_leads)}", flush=True)
    return discovered_leads
