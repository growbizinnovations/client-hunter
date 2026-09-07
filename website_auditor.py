import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse

from db_manager import save_website_audit

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def extract_copyright_year(text: str) -> Optional[int]:
    """Finds the most recent copyright year mentioned on the page."""
    current_year = datetime.now().year
    # Match patterns like: (c) 2014, Copyright 2016, © 2010-2018
    matches = re.findall(r'(?:©|&copy;|copyright|\(c\))\s*(?:(?:\d{4}\s*[-–—]\s*)?)(20\d\d)', text, re.IGNORECASE)
    if matches:
        years = [int(y) for y in matches if 1995 <= int(y) <= current_year + 1]
        if years:
            return max(years)
    return None

def audit_website(lead_id: int, url: str) -> Dict[str, Any]:
    """
    Performs a deep audit of a website to identify outdated elements,
    performance bottlenecks, mobile friendliness issues, and obsolete tech.
    """
    start_time = time.time()
    issues: List[str] = []
    positive_cues: List[str] = []
    outdated_score = 0
    
    parsed = urlparse(url)
    target_url = url
    if not parsed.scheme:
        target_url = f"http://{url}"
        
    has_ssl = True
    copyright_year = None
    is_responsive = True
    has_viewport = True
    uses_tables = False
    uses_flash = False
    legacy_jquery = False
    load_time_sec = 0.0
    html_size_kb = 0.0
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    try:
        # Check SSL / connection
        response = requests.get(target_url, headers=headers, timeout=12, allow_redirects=True)
        load_time_sec = round(time.time() - start_time, 2)
        final_url = response.url
        
        if not final_url.startswith("https://"):
            has_ssl = False
            outdated_score += 25
            issues.append("Website is missing SSL/HTTPS encryption (marked 'Not Secure' in modern browsers)")
            
        html_content = response.text
        html_size_kb = round(len(html_content.encode("utf-8")) / 1024.0, 1)
        
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 1. Viewport & Mobile Check
        viewport_tag = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
        if not viewport_tag:
            has_viewport = False
            is_responsive = False
            outdated_score += 35
            issues.append("Missing mobile viewport configuration (layout requires manual pinching/zooming on smartphones)")
            
        # 2. Copyright Year Check
        page_text = soup.get_text()
        copyright_year = extract_copyright_year(page_text)
        current_year = datetime.now().year
        
        if copyright_year:
            if copyright_year < current_year - 4: # e.g. 2022 or older
                outdated_score += 30
                issues.append(f"Footer copyright date is outdated (shows © {copyright_year})")
            elif copyright_year < current_year - 1:
                outdated_score += 15
                issues.append(f"Copyright is not current (displays © {copyright_year})")
        else:
            outdated_score += 10
            issues.append("No updated copyright or recent business activity date found")
            
        # 3. Obsolete Tech & Scripts
        scripts = [s.get("src", "") for s in soup.find_all("script") if s.get("src")]
        scripts_text = " ".join(scripts).lower()
        
        if "flash" in html_content.lower() or soup.find("object") or soup.find("embed"):
            uses_flash = True
            outdated_score += 40
            issues.append("Legacy Adobe Flash or embedded media elements detected (unsupported on modern mobile/desktop)")
            
        if re.search(r'jquery[\.-]1\.', scripts_text):
            legacy_jquery = True
            outdated_score += 20
            issues.append("Runs an obsolete jQuery 1.x library with known security vulnerabilities and slow DOM rendering")
            
        # 4. Table-based layout
        tables = soup.find_all("table")
        if len(tables) > 4 or any("layout" in str(t.get("class", "")).lower() or t.get("width") for t in tables):
            uses_tables = True
            outdated_score += 25
            issues.append("Uses legacy HTML tables for page layout instead of modern CSS Grid/Flexbox")
            
        # 5. Missing OpenGraph & Social Metadata
        og_title = soup.find("meta", attrs={"property": "og:title"})
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if not og_title or not og_image:
            outdated_score += 10
            issues.append("Missing social share / OpenGraph metadata (links display as blank thumbnails when shared on iMessage/WhatsApp/Social)")
            
        # 6. Page Speed / Load Time
        if load_time_sec > 4.5:
            outdated_score += 15
            issues.append(f"Slow initial page load time ({load_time_sec}s), causing potential customer drop-off")
            
        # Modern platforms detection - only if no major layout/ssl flaws
        is_modern_builder = any(keyword in html_content.lower() for keyword in ["wp-content/themes/framer", "webflow", "squarespace", "shopify", "framer.com", "wix.com"])
        if is_modern_builder and not uses_tables and not uses_flash and has_viewport:
            outdated_score = max(0, outdated_score - 20)
            positive_cues.append("Uses a modern CMS platform")
            
    except Exception as e:
        load_time_sec = round(time.time() - start_time, 2)
        outdated_score += 20
        issues.append(f"Connection error or server latency: {str(e)[:100]}")
        
    # Any website with detected layout/tech/copyright flaws is classified as OUTDATED (Target for Redesign)
    is_outdated = (outdated_score >= 15 or len(issues) >= 1)
    
    # Generate human readable audit summary
    if is_outdated:
        summary = f"Outdated Website (Flaws Detected: {len(issues)}). High-potential redesign target."
    else:
        summary = f"Modern Website (Design Score: 100/100). Well-maintained."
        
    # Save to database
    save_website_audit(
        lead_id=lead_id,
        is_outdated=is_outdated,
        score=outdated_score,
        copyright_year=copyright_year,
        is_responsive=is_responsive,
        has_ssl=has_ssl,
        has_viewport=has_viewport,
        uses_tables=uses_tables,
        uses_flash=uses_flash,
        legacy_jquery=legacy_jquery,
        load_time=load_time_sec,
        html_size_kb=html_size_kb,
        issues=issues,
        positive_cues=positive_cues,
        summary=summary
    )
    
    print(f"[Audit] Lead #{lead_id} ({url}) -> Score: {outdated_score} | Outdated: {is_outdated} | Issues: {len(issues)}")
    return {
        "lead_id": lead_id,
        "is_outdated": is_outdated,
        "outdated_score": outdated_score,
        "copyright_year": copyright_year,
        "issues": issues,
        "summary": summary
    }
