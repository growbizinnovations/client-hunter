import json
import os
import requests
from typing import Dict, Any, List, Optional
from settings import settings

def call_openai_chat(prompt: str) -> Optional[str]:
    """Calls OpenAI API directly via requests (works with any key format)."""
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

def create_template_pitch(business_name: str, city: str, state: str, domain: str, issues: List[str]) -> Dict[str, str]:
    issue_desc = "a few quick mobile and display fixes"
    if issues:
        first = issues[0].lower()
        if "ssl" in first:
            issue_desc = "missing SSL security"
        elif "mobile" in first or "viewport" in first:
            issue_desc = "mobile display alignment issues on smartphones"
        elif "copyright" in first:
            issue_desc = "an outdated copyright and layout"
            
    subject = f"Quick question regarding {domain}"
    body_text = f"""Hi {business_name} team,

I came across your site ({domain}) while researching local businesses in {city} and noticed {issue_desc}.

We build clean, mobile-friendly websites that turn visitors into paying clients.

I'd love to put together a 100% free redesign demo for {business_name}. If you love it, it's just a flat ${settings.REDESIGN_OFFER_PRICE} to launch. If not, you owe nothing.

Would you be open to seeing a free preview?

Best,
{settings.SENDER_NAME}"""
    return {"subject": subject, "body_text": body_text}

def generate_personalized_pitch(business_name: str, city: str, state: str, domain: str, niche: str, issues: List[str]) -> Dict[str, str]:
    prompt = f"""
Write an extremely short, punchy, high-converting B2B cold email (STRICTLY 50 to 70 words total).
Prospect: {business_name} ({niche} in {city}, {state}, domain: {domain}).
Website issues: {json.dumps(issues[:2])}

Offer:
- 100% FREE custom website redesign preview / demo.
- If they want to keep and launch it, flat ${settings.REDESIGN_OFFER_PRICE}. If not, $0.
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
    return create_template_pitch(business_name, city, state, domain, issues)

def generate_followup_email(business_name: str, city: str, original_subject: str, step: int) -> Dict[str, str]:
    subject = f"Re: {original_subject}"
    if step == 1:
        body_text = f"""Hi {business_name} team,

Just following up on my quick note about {business_name}'s website.

We'd still love to build you a free redesign preview to show how a faster mobile layout can bring in more local customers in {city}.

If interested, just reply and I'll send over the free demo link.

Best,
{settings.SENDER_NAME}"""
    else:
        body_text = f"""Hi {business_name} team,

I know you're busy, so this will be my last note!

If you ever want a fresh, modern website for {business_name} (just ${settings.REDESIGN_OFFER_PRICE} flat to launch if you love the demo), feel free to reach out anytime.

Wishing you all the best!

Best,
{settings.SENDER_NAME}"""
    return {"subject": subject, "body_text": body_text}
    return {"subject": subject, "body_text": body_text}
