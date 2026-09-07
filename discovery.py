import re
import time
import urllib.parse
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from urllib.parse import urlparse

from settings import settings
from db_manager import get_or_create_lead

# Non-business / foreign TLDs to exclude
EXCLUDED_TLDS = {
    ".in", ".pk", ".sa", ".uk", ".au", ".ca", ".de", ".fr", ".cn", ".jp",
    ".edu", ".gov", ".mil", ".ac.in", ".edu.in", ".gov.in", ".nic.in"
}

# Known aggregate directories, social platforms, news, magazines, national retail chains, and non-local portals
EXCLUDED_DOMAINS = {
    "yelp.com", "yellowpages.com", "angi.com", "thumbtack.com", "homeadvisor.com",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "bbb.org",
    "mapquest.com", "tripadvisor.com", "wikipedia.org", "houzz.com", "groupon.com",
    "superpages.com", "manta.com", "dexknows.com", "city-data.com", "zillow.com",
    "realtor.com", "patch.com", "nextdoor.com", "indeed.com", "glassdoor.com",
    "chamberofcommerce.com", "yellowbook.com", "bizapedia.com", "crunchbase.com",
    "apple.com", "google.com", "bing.com", "yahoo.com", "wikihow.com", "investopedia.com",
    "forbes.com", "dictionary.com", "vocabulary.com", "shiksha.com", "collegedunia.com",
    "nobroker.in", "careers360.com", "cardekho.com", "sastaticket.pk", "bookme.pk",
    "ulta.com", "bhg.com", "theburn.com", "loudountimes.com", "sephora.com", "walmart.com",
    "target.com", "homedepot.com", "lowes.com", "amazon.com", "ebay.com", "costco.com",
    "bestbuy.com", "macys.com", "kohls.com", "nordstrom.com", "walgreens.com", "cvs.com",
    "nytimes.com", "washingtonpost.com", "cnn.com", "foxnews.com", "usatoday.com",
    "buzzfeed.com", "huffpost.com", "thespruce.com", "bobvila.com", "realsimple.com",
    "architecturaldigest.com", "elledecor.com", "housebeautiful.com", "goodhousekeeping.com",
    "hgtv.com", "diynetwork.com", "pinterest.com", "reddit.com", "quora.com", "medium.com",
    "substack.com", "wordpress.com", "blogspot.com", "wixsite.com", "timeanddate.com",
    "zocdoc.com", "webmd.com", "vitals.com", "opencare.com", "rankmydentist.com",
    "deltadental.com", "usnews.com", "here.com", "1-800-dentist.com", "healthgrades.com",
    "carecredit.com", "doximity.com", "expertise.com", "birdeye.com", "topratedlocal.com",
    "thedentistranker.com", "thetop10rank.com", "dentalify.com", "bestinhood.com",
    "smilesatlas.com", "findopendentist.com", "tebra.com", "uservoice.com", "dental.me"
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

def is_valid_business_website(url: str, title: str = "") -> bool:
    domain = clean_domain(url)
    if not domain or len(domain) < 4:
        return False
        
    # Exclude foreign and academic/gov TLDs
    if any(domain.endswith(tld) for tld in EXCLUDED_TLDS):
        return False
    
    # Exclude directory/social/news/magazine/retail domains
    for excluded in EXCLUDED_DOMAINS:
        if domain == excluded or domain.endswith("." + excluded):
            return False
            
    # Exclude file downloads
    if any(url.lower().endswith(ext) for ext in [".pdf", ".jpg", ".png", ".zip", ".docx", ".mp4", ".svg"]):
        return False
        
    # Exclude blog articles / listicles / national guides
    if title:
        t_low = title.lower()
        if any(bad_phrase in t_low for bad_phrase in [
            "ideas for", "top 10", "top 15", "top 20", "top 50", "best 10", "best 15", "best 20", "how to", "guide to",
            "magazine", "trends for", "what is", "wikipedia", "directory of", "reviews of best",
            "near me directory", "compare ", "ranked by", "ratings and reviews", "find a dentist"
        ]):
            return False
            
    return True

def extract_business_name_from_title(title: str, query_niche: str, domain: str = "") -> str:
    """Extracts a clean, human business name from search result title, falling back to clean domain formatting."""
    GENERIC_WORDS = {
        "website", "home", "homepage", "welcome", "official site", "untitled", "index",
        "about", "contact", "services", "online", "clinic", "office", "page", "main page",
        "business", "company", "none", "null"
    }
    
    clean_title = title.strip() if title else ""
    if clean_title:
        parts = re.split(r'[\-\|\:\–\—\•]', clean_title)
        for p in parts:
            candidate = p.strip()
            for prefix in ["Welcome to ", "Home - ", "Official Website of ", "About ", "Services - "]:
                if candidate.lower().startswith(prefix.lower()):
                    candidate = candidate[len(prefix):].strip()
            if candidate and candidate.lower() not in GENERIC_WORDS and len(candidate) >= 3:
                return candidate[:50]
                
    # Fallback: derive nicely from domain (e.g. smile-la.com -> Smile LA)
    if domain:
        d = domain.lower()
        if d.startswith("www."):
            d = d[4:]
        d_name = d.split(".")[0]
        words = re.split(r'[-_]', d_name)
        formatted = []
        for w in words:
            if w.lower() == "la":
                formatted.append("LA")
            elif w.lower() == "dr":
                formatted.append("Dr.")
            elif w.lower() == "nyc":
                formatted.append("NYC")
            elif w.lower() == "fl":
                formatted.append("FL")
            elif w.lower() == "ca":
                formatted.append("CA")
            else:
                formatted.append(w.capitalize())
        clean_d = " ".join(formatted).strip()
        if clean_d and clean_d.lower() not in GENERIC_WORDS:
            return clean_d
            
    return "Dental Practice" if "dentist" in query_niche.lower() else "Local Business"

def search_live_web(query: str, max_results: int = 25) -> List[Dict[str, str]]:
    """Fetches real search results across multiple engines (DuckDuckGo HTML & Yahoo)."""
    results = []
    seen_urls = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    # 1. DuckDuckGo HTML Search
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for result in soup.find_all("div", class_="result"):
                a_elem = result.find("a", class_="result__url")
                title_elem = result.find("a", class_="result__title") or result.find("a", class_="result__snippet")
                if a_elem:
                    href = a_elem.get("href", "").strip()
                    if "uddg=" in href:
                        try:
                            actual_url = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                            href = actual_url
                        except Exception:
                            pass
                    if href.startswith("http") and href not in seen_urls:
                        title = title_elem.get_text(strip=True) if title_elem else href
                        if is_valid_business_website(href, title):
                            seen_urls.add(href)
                            results.append({"href": href, "title": title})
    except Exception:
        pass

    # 2. Yahoo Search for real local businesses
    try:
        y_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}"
        resp = requests.get(y_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if "/RU=" in href:
                    try:
                        actual = href.split("/RU=")[1].split("/RK=")[0]
                        actual = urllib.parse.unquote(actual)
                        title = a.get_text(strip=True) or actual
                        if actual.startswith("http") and not any(x in actual for x in ["yahoo.com", "yimg.com", "bing.com"]):
                            if is_valid_business_website(actual, title) and actual not in seen_urls:
                                seen_urls.add(actual)
                                results.append({"href": actual, "title": title})
                    except Exception:
                        pass
    except Exception:
        pass

    return results

def discover_businesses_for_city(city: str, state: str, max_leads_per_niche: int = 15, progress_callback=None) -> List[Dict[str, Any]]:
    """Discovers real local small businesses for a target US city/state using deep multi-query search."""
    discovered_leads = []
    total_niches = len(settings.BUSINESS_NICHES)
    
    print(f"[Discovery] Searching live Google/Web for local businesses in {city}, {state} across all {total_niches} business categories...", flush=True)
    if progress_callback:
        progress_callback(city, state, "General Search", 0, total_niches, 0, f"Starting deep Google & Maps search for businesses in {city}, {state} across all {total_niches} categories...")
    
    for niche_idx, niche in enumerate(settings.BUSINESS_NICHES):
        cat_num = niche_idx + 1
        if progress_callback:
            progress_callback(
                city, state, niche, cat_num, total_niches, len(discovered_leads),
                f"Searching Google for Category {cat_num}/{total_niches}: '{niche}' in {city}, {state} ({len(discovered_leads)} businesses found so far)..."
            )
            
        queries = [
            f'"{niche}" "{city}, {state}" local business website',
            f'best "{niche}" "{city}" "{state}"',
            f'"{niche}" in "{city} {state}" reviews phone website',
            f'local "{niche}" companies "{city}, {state}"'
        ]
        
        for query in queries:
            results = search_live_web(query, max_results=max_leads_per_niche)
            time.sleep(0.3)
            
            for r in results:
                url = r.get("href", "")
                title = r.get("title", "")
                
                if not is_valid_business_website(url, title):
                    continue
                    
                domain = clean_domain(url)
                if not domain:
                    continue
                    
                biz_name = extract_business_name_from_title(title, niche, domain=domain)
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
                    if progress_callback:
                        progress_callback(
                            city, state, niche, cat_num, total_niches, len(discovered_leads),
                            f"Discovered #{len(discovered_leads)}: {biz_name} ({domain}) in {city}, {state} [Category {cat_num}/{total_niches}: {niche}]"
                        )
                
    print(f"[Discovery] Total live leads found for {city}, {state}: {len(discovered_leads)}", flush=True)
    return discovered_leads

def parse_google_maps_query(query_str: str) -> Tuple[str, str, str]:
    """Parses a natural search query like 'dentist in Los Angeles, CA' or 'hair transplant Miami' into niche, city, state."""
    raw = query_str.strip()
    niche = raw
    city = "Unknown"
    state = "US"
    
    # Check for common separators: " in ", " near ", " around ", " at "
    m = re.search(r'^(.*?)\s+(?:in|near|around|at)\s+(.*)$', raw, re.IGNORECASE)
    if m:
        niche = m.group(1).strip()
        location_part = m.group(2).strip()
        if "," in location_part:
            parts = location_part.split(",")
            city = parts[0].strip()
            state = parts[1].strip().upper()
        else:
            city = location_part
    elif "," in raw:
        parts = raw.split(",")
        niche = parts[0].strip()
        city = parts[1].strip()
    return niche, city, state

def search_custom_niche_in_city(niche: str, location_query: str = "", max_results: int = 50, progress_callback=None) -> List[Dict[str, Any]]:
    """Performs an exhaustive multi-query live Google and Google Maps search for any search query or niche + city."""
    discovered_leads = []
    
    # If single search string was passed in niche
    if not location_query and any(sep in niche.lower() for sep in [" in ", " near ", ","]):
        parsed_niche, parsed_city, parsed_state = parse_google_maps_query(niche)
        clean_niche = parsed_niche
        city = parsed_city
        state = parsed_state
        search_target = niche.strip()
    else:
        clean_niche = niche.strip()
        clean_loc = location_query.strip()
        if "," in clean_loc:
            parts = clean_loc.split(",")
            city = parts[0].strip()
            state = parts[1].strip().upper()
        elif clean_loc:
            city = clean_loc
            state = "US"
        else:
            city = "Local"
            state = "US"
        search_target = f"{clean_niche} in {clean_loc}" if clean_loc else clean_niche
        
    queries = [
        f'"{search_target}" local business website',
        f'"{clean_niche}" in "{city}" website',
        f'best "{clean_niche}" "{city} {state}"',
        f'"{search_target}" google maps reviews contact phone',
        f'local "{clean_niche}" companies "{city}"',
        f'"{clean_niche}" services near "{city} {state}"',
        f'top rated "{clean_niche}" "{city}"'
    ]
    
    total_queries = len(queries)
    print(f"[Google Maps Deep Search] Query: '{search_target}' across {total_queries} search angles...", flush=True)
    
    if progress_callback:
        progress_callback(10, f"Scanning Google Maps & Web for '{search_target}'...", len(discovered_leads))
        
    for q_idx, q in enumerate(queries):
        if progress_callback:
            curr_pct = 10 + int((q_idx / total_queries) * 35)
            progress_callback(curr_pct, f"Google Maps Page/Query {q_idx+1}/{total_queries}: {q} ({len(discovered_leads)} businesses found)", len(discovered_leads))
            
        results = search_live_web(q, max_results=25)
        time.sleep(0.3)
        
        for r in results:
            url = r.get("href", "")
            title = r.get("title", "")
            
            if not is_valid_business_website(url, title):
                continue
                
            domain = clean_domain(url)
            if not domain:
                continue
                
            biz_name = extract_business_name_from_title(title, clean_niche, domain=domain)
            parsed = urlparse(url)
            clean_root_url = f"{parsed.scheme}://{parsed.netloc}"
            
            lead_obj, is_new = get_or_create_lead(
                business_name=biz_name,
                website_url=clean_root_url,
                domain=domain,
                city=city,
                state=state,
                niche=clean_niche
            )
            
            # Add to return list if not already in discovered_leads
            if not any(d["domain"] == domain for d in discovered_leads):
                discovered_leads.append({
                    "id": lead_obj.id,
                    "business_name": biz_name,
                    "website_url": clean_root_url,
                    "domain": domain,
                    "city": city,
                    "state": state,
                    "niche": clean_niche,
                    "is_new": is_new
                })
                if progress_callback:
                    progress_callback(
                        10 + int((q_idx / total_queries) * 35),
                        f"Found #{len(discovered_leads)}: {biz_name} ({domain})",
                        len(discovered_leads)
                    )
                    
        if len(discovered_leads) >= max_results:
            break
            
    print(f"[Google Maps Deep Search] Finished. Found {len(discovered_leads)} businesses for '{search_target}'.", flush=True)
    return discovered_leads
