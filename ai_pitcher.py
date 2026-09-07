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
    bullet_points = ""
    if issues:
        clean_issues = [f"• {issue}" for issue in issues[:3]]
        bullet_points = "\n".join(clean_issues)
    else:
        bullet_points = "• Mobile display alignment issues on modern smartphone screens\n• Insecure HTTP connection (missing SSL certificate)\n• Outdated copyright year and slow page load speed"
        
    subject = f"Quick question regarding {business_name}'s website in {city}"
    body_text = f"""Hi {business_name} Team,

I came across your website ({domain}) while researching established businesses in {city}, {state}. You guys do great work in the area, but I noticed a few technical and design things on your site that might be costing you potential customers:

{bullet_points}

We specialize in modern, mobile-friendly websites that convert visitors into paying clients.

To make this completely risk-free: we would love to build you a free custom redesign demo. If you're interested, just reply to this email with any specific changes, new services, or style preferences you'd like (or we can modernize the entire layout from scratch), and we'll build and send over a demo link for you to review.

If you love the demo and want to launch it, we do the full handover and setup for a flat ${settings.REDESIGN_OFFER_PRICE}. If not, no worries at all and you owe nothing.

Would you be open to seeing a free custom demo for {business_name}?

Best regards,

{settings.SENDER_NAME}
"""
    return {"subject": subject, "body_text": body_text}

def generate_personalized_pitch(business_name: str, city: str, state: str, domain: str, niche: str, issues: List[str]) -> Dict[str, str]:
    prompt = f"""
Write a concise, friendly, authentic, and high-converting cold email offering a free website redesign demo.

Business Details:
- Name: {business_name}
- Industry/Niche: {niche}
- City/State: {city}, {state}
- Website Domain: {domain}
- Website Audit Flaws Found: {json.dumps(issues)}

Offer:
- Build and send a 100% FREE custom website redesign demo.
- If they like it, full launch is flat ${settings.REDESIGN_OFFER_PRICE}. If not, zero cost.
- Ask them to reply with what they'd like changed so we can build the demo.
- Sender: {settings.SENDER_NAME} (no title).
- NO calendar links or phone calls. Strictly over email.

Return JSON with keys "subject" and "body_text".
"""
    # 1. Try OpenAI if key is present
    if settings.OPENAI_API_KEY:
        raw_json = call_openai_chat(prompt)
        if raw_json:
            try:
                data = json.loads(raw_json)
                return {"subject": data.get("subject"), "body_text": data.get("body_text")}
            except Exception:
                pass
                
    # 2. Try Gemini if key is present
    if settings.GEMINI_API_KEY:
        raw_json = call_gemini_chat(prompt)
        if raw_json:
            try:
                data = json.loads(raw_json)
                return {"subject": data.get("subject"), "body_text": data.get("body_text")}
            except Exception:
                pass
                
    # 3. Smart Template Fallback
    return create_template_pitch(business_name, city, state, domain, issues)

def generate_followup_email(business_name: str, city: str, original_subject: str, step: int) -> Dict[str, str]:
    subject = f"Re: {original_subject}"
    if step == 1:
        body_text = f"""Hi {business_name} Team,

Just following up on my previous note regarding your website.

We'd still love to build a free custom redesign demo for {business_name} to show you how a faster, modern layout can help bring in more local leads in {city}.

If you have any specific changes or features in mind (or want us to put together a fresh modern look), just reply back and let us know what you'd like to update so we can build the demo for you.

Best regards,

{settings.SENDER_NAME}
"""
    else:
        body_text = f"""Hi {business_name} Team,

I know you're busy running operations at {business_name}, so I'll make this my last follow-up!

If you ever want to upgrade your website down the road or want to see a free custom demo built for just ${settings.REDESIGN_OFFER_PRICE} if you love it, feel free to reply to this email anytime with what you'd like changed.

Wishing {business_name} all the best!

Best regards,

{settings.SENDER_NAME}
"""
    return {"subject": subject, "body_text": body_text}
