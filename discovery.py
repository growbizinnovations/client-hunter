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

def search_live_web(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Fetches real search results from DuckDuckGo HTML and DDGS."""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    # 1. Try DuckDuckGo HTML directly
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for result in soup.find_all("div", class_="result"):
                a_elem = result.find("a", class_="result__url")
                title_elem = result.find("a", class_="result__snippet") or result.find("a", class_="result__title")
                if a_elem:
                    href = a_elem.get("href", "").strip()
                    # unwrap uddg redirect if present
                    if "uddg=" in href:
                        try:
                            actual_url = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                            href = actual_url
                        except Exception:
                            pass
                    if href.startswith("http"):
                        title = title_elem.get_text(strip=True) if title_elem else href
                        results.append({"href": href, "title": title})
    except Exception:
        pass

    # 2. Try DDGS API
    if len(results) < max_results:
        try:
            ddgs = DDGS()
            for r in ddgs.text(query, region="us-en", max_results=max_results + 3):
                if r.get("href"):
                    results.append({"href": r["href"], "title": r.get("title", "")})
        except Exception:
            pass

    return results

def discover_businesses_for_city(city: str, state: str, max_leads_per_niche: int = 4, progress_callback=None) -> List[Dict[str, Any]]:
    """Discovers real local small businesses for a target US city/state using live search engines."""
    discovered_leads = []
    
    print(f"[Discovery] Searching live Google/Web for local businesses in {city}, {state}...", flush=True)
    if progress_callback:
        progress_callback(city, state, "General Search", 0, len(settings.BUSINESS_NICHES), f"Searching Google Maps & Web for local businesses in {city}, {state}...")
    
    for niche_idx, niche in enumerate(settings.BUSINESS_NICHES):
        if progress_callback:
            progress_callback(city, state, niche, niche_idx + 1, len(settings.BUSINESS_NICHES), f"Searching Google for: '{niche}' in {city}, {state} ({niche_idx+1}/{len(settings.BUSINESS_NICHES)})...")
            
        queries = [
            f'"{niche}" "{city}, {state}" local business website',
            f'best "{niche}" "{city}" "{state}"'
        ]
        
        for query in queries:
            results = search_live_web(query, max_results=max_leads_per_niche + 2)
            time.sleep(0.3)
            
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
                    print(f"  [+] Discovered live business: {biz_name} ({domain}) - {niche}", flush=True)
                    discovered_leads.append({
                        "id": lead_obj.id,
                        "business_name": biz_name,
                        "website_url": clean_root_url,
                        "domain": domain,
                        "city": city,
                        "state": state,
                        "niche": niche
                    })
                
    print(f"[Discovery] Total live leads found for {city}, {state}: {len(discovered_leads)}", flush=True)
    return discovered_leads
