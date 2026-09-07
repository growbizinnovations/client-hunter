import json
import os
import re
import requests
from typing import Dict, Any, List, Optional
from settings import settings

GENERIC_NAMES = {
    "website", "home", "homepage", "welcome", "official site", "untitled", "index",
    "about", "contact", "services", "online", "clinic", "office", "page", "main page",
    "business", "company", "services in", "near me", "none", "null"
}

def clean_prospect_name(business_name: str, domain: str, niche: str = "") -> str:
    """Derives a clean, natural business or doctor name for email personalization."""
    raw = business_name.strip() if business_name else ""
    
    # Check if raw name is valid and not generic
    if raw and raw.lower() not in GENERIC_NAMES and raw.lower() != domain.lower() and len(raw) >= 3:
        # If it contains pipes or hyphens, take the leading part
        parts = re.split(r'[\-\|\:\–\—\•]', raw)
        candidate = parts[0].strip()
        for prefix in ["Welcome to ", "Home - ", "Official Website of ", "About "]:
            if candidate.lower().startswith(prefix.lower()):
                candidate = candidate[len(prefix):].strip()
        if candidate and candidate.lower() not in GENERIC_NAMES and len(candidate) >= 3:
            return candidate[:45]

    # Derive from domain (e.g. smile-la.com -> Smile LA, drkezian.com -> Dr. Kezian)
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
        if clean_d and clean_d.lower() not in GENERIC_NAMES:
            return clean_d
            
    return "your practice" if "dentist" in niche.lower() else "your business"

def call_openai_chat(prompt: str) -> Optional[str]:
    """Calls OpenAI API directly via requests."""
    if not settings.OPENAI_API_KEY:
        return None
    try:
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are an expert B2B cold email copywriter. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7
        }
        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[AI Pitcher] OpenAI API error: {e}")
    return None

def call_gemini_chat(prompt: str) -> Optional[str]:
    """Calls Google Gemini API."""
    if not settings.GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY.strip())
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return resp.text
    except Exception as e:
        print(f"[AI Pitcher] Gemini API error: {e}")
    return None

def create_template_pitch(business_name: str, city: str, state: str, domain: str, issues: List[str], niche: str = "business") -> Dict[str, str]:
    clean_name = clean_prospect_name(business_name, domain, niche)
    
    # Natural personalized greeting
    if clean_name.lower().startswith("dr.") or clean_name.lower().startswith("dr "):
        greeting = f"Hi {clean_name},"
    elif clean_name.lower() in ["your practice", "your business", "your team"]:
        greeting = "Hi there,"
    else:
        greeting = f"Hi {clean_name} team,"
        
    issue_desc = "a few mobile display alignment issues on smartphones"
    if issues:
        first = issues[0].lower()
        if "ssl" in first:
            issue_desc = "missing SSL security"
        elif "mobile" in first or "viewport" in first:
            issue_desc = "mobile layout alignment issues on smartphones"
        elif "copyright" in first:
            issue_desc = "an outdated copyright and layout"
        elif "slow" in first or "load" in first:
            issue_desc = "slow mobile loading speeds"
            
    subject = f"Quick question regarding {domain}"
    demo_target = f"your practice in {city}" if clean_name.lower() in ["your practice", "your business"] else clean_name

    body_text = f"""{greeting}

I came across your site ({domain}) while researching local businesses in {city} and noticed {issue_desc}.

We build clean, fast, mobile-friendly websites that turn visitors into paying clients.

I'd love to put together a 100% free redesign demo for {demo_target}. If you love it, it's just a flat ${settings.REDESIGN_OFFER_PRICE} to launch. If not, you owe nothing.

Would you be open to seeing a free preview?

Best,
{settings.SENDER_NAME}"""
    return {"subject": subject, "body_text": body_text}

def generate_personalized_pitch(business_name: str, city: str, state: str, domain: str, niche: str, issues: List[str]) -> Dict[str, str]:
    clean_name = clean_prospect_name(business_name, domain, niche)
    
    prompt = f"""
Write an extremely short, punchy, human, high-converting B2B cold email (STRICTLY 50 to 70 words total).
Prospect: {clean_name} ({niche} in {city}, {state}, domain: {domain}).
Website issues: {json.dumps(issues[:2])}

Rules:
- Greeting: If name is a doctor, 'Hi Dr. [Name],'. Otherwise 'Hi {clean_name} team,'. NEVER say 'Hi Website team'.
- Offer: 100% FREE custom website redesign preview / demo. If they want to keep and launch it, flat ${settings.REDESIGN_OFFER_PRICE}. If not, $0.
- Sender: {settings.SENDER_NAME} (no company or title).
- Short CTA: Would you be open to seeing a quick free preview?
- STRICT WORD LIMIT: 50 - 70 words.

Return JSON with keys "subject" and "body_text".
"""
    # 1. Try OpenAI if key is present
    if settings.OPENAI_API_KEY:
        raw_json = call_openai_chat(prompt)
        if raw_json:
            try:
                data = json.loads(raw_json)
                if data.get("subject") and data.get("body_text"):
                    return {"subject": data.get("subject"), "body_text": data.get("body_text")}
            except Exception:
                pass
                
    # 2. Try Gemini if key is present
    if settings.GEMINI_API_KEY:
        raw_json = call_gemini_chat(prompt)
        if raw_json:
            try:
                data = json.loads(raw_json)
                if data.get("subject") and data.get("body_text"):
                    return {"subject": data.get("subject"), "body_text": data.get("body_text")}
            except Exception:
                pass
                
    # 3. Smart Template Fallback
    return create_template_pitch(clean_name, city, state, domain, issues, niche)

def generate_followup_email(business_name: str, city: str, original_subject: str, step: int) -> Dict[str, str]:
    clean_name = clean_prospect_name(business_name, "", "business")
    greeting = f"Hi {clean_name} team," if clean_name.lower() not in ["your business", "your practice"] else "Hi there,"
    subject = f"Re: {original_subject}"
    if step == 1:
        body_text = f"""{greeting}

Just following up on my quick note about your website.

We'd still love to build you a free redesign preview to show how a faster mobile layout can bring in more local customers in {city}.

If interested, just reply and I'll send over the free demo link.

Best,
{settings.SENDER_NAME}"""
    else:
        body_text = f"""{greeting}

I know you're busy, so this will be my last note!

If you ever want a fresh, modern website for {clean_name} (just ${settings.REDESIGN_OFFER_PRICE} flat to launch if you love the demo), feel free to reach out anytime.

Wishing you all the best!

Best,
{settings.SENDER_NAME}"""
    return {"subject": subject, "body_text": body_text}
