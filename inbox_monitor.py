import imaplib
import email
from email.header import decode_header
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from settings import settings
from db_manager import SessionLocal
from models import Lead, InboxMessage, EmailCampaign
from sender import send_single_email

# Attempt Gemini AI for classification
HAS_GEMINI = False
try:
    if settings.GEMINI_API_KEY:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        HAS_GEMINI = True
except Exception:
    HAS_GEMINI = False

def classify_reply_intent(email_body: str) -> str:
    """Classifies the prospect's intent: INTERESTED, NOT_INTERESTED, UNSUBSCRIBE, QUESTION, or AUTO_REPLY."""
    lower_body = email_body.lower()
    
    # Heuristic checks
    if any(phrase in lower_body for phrase in ["unsubscribe", "remove me", "stop emailing", "do not contact"]):
        return "UNSUBSCRIBE"
    if any(phrase in lower_body for phrase in ["out of office", "auto-reply", "automatic reply", "on vacation"]):
        return "AUTO_REPLY"
    if any(phrase in lower_body for phrase in ["not interested", "no thank you", "no thanks", "already have", "we have an in-house team"]):
        return "NOT_INTERESTED"
    if any(phrase in lower_body for phrase in ["send the preview", "send demo", "show me", "interested", "how much", "sounds good", "free demo", "what do you need", "send me the link"]):
        return "INTERESTED"
        
    if not HAS_GEMINI or not settings.GEMINI_API_KEY:
        return "INTERESTED" if len(email_body.strip()) > 5 else "QUESTION"
        
    prompt = f"""
Analyze this prospect's reply to our cold outreach email offering to build a free website redesign demo for $500.
Classify the intent into one of these exact categories:
- INTERESTED
- NOT_INTERESTED
- UNSUBSCRIBE
- QUESTION
- AUTO_REPLY

Reply text:
\"\"\"{email_body}\"\"\"

Return a JSON object with key "intent".
"""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(resp.text)
        return data.get("intent", "QUESTION")
    except Exception:
        return "INTERESTED"

def craft_positive_requirements_reply(business_name: str, sender_name: str) -> str:
    """Drafts an email asking the prospect for their specific website requirements so you can build the demo."""
    return f"""Hi {business_name} Team,

Thanks for getting back to me! We're excited to put together your free custom redesign demo.

To make sure the demo matches exactly what you're looking for, could you reply back with a few quick details:

1. What are the main things or issues you'd like changed/fixed from your current website?
2. Are there any specific services, special offers, or customer reviews you want prominently featured on the homepage?
3. Are there any websites (competitors or others) whose design style or colors you like?

As soon as you reply with your thoughts, we'll start building your custom demo and send over the preview link for you to review within 48 hours!

Best regards,

{settings.SENDER_NAME}
"""

def check_account_inbox(account_email: str, account_pass: str) -> List[Dict[str, Any]]:
    """Checks an individual Gmail account for unread replies via IMAP."""
    if settings.DRY_RUN or not account_email or not account_pass:
        return []
        
    replies_found = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(account_email, account_pass)
        mail.select("inbox")
        
        status, messages = mail.search(None, '(UNSEEN)')
        if status != "OK":
            return []
            
        email_ids = messages[0].split()
        for e_id in email_ids:
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    sender = msg.get("From", "")
                    sender_email_match = re.search(r'[\w\.-]+@[\w\.-]+', sender)
                    sender_email = sender_email_match.group(0).lower() if sender_email_match else sender
                    
                    subject_header = msg.get("Subject", "")
                    decoded_subject = ""
                    for s, enc in decode_header(subject_header):
                        if isinstance(s, bytes):
                            decoded_subject += s.decode(enc if enc else "utf-8", errors="ignore")
                        else:
                            decoded_subject += str(s)
                            
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                        
                    intent = classify_reply_intent(body)
                    
                    session = SessionLocal()
                    try:
                        lead = session.query(Lead).join(Lead.contacts).filter(Lead.contacts.any(email=sender_email)).first()
                        
                        inbox_msg = InboxMessage(
                            lead_id=lead.id if lead else None,
                            sender_email=sender_email,
                            recipient_account=account_email,
                            subject=decoded_subject,
                            body=body,
                            classified_intent=intent,
                            received_at=datetime.utcnow()
                        )
                        session.add(inbox_msg)
                        
                        if lead:
                            if intent == "INTERESTED":
                                lead.status = "REPLIED"
                                auto_text = craft_positive_requirements_reply(lead.business_name, settings.SENDER_NAME)
                                send_single_email(
                                    sender_email=account_email,
                                    sender_password=account_pass,
                                    recipient_email=sender_email,
                                    subject=f"Re: {decoded_subject}",
                                    body_text=auto_text
                                )
                                inbox_msg.auto_responded = True
                                inbox_msg.auto_response_text = auto_text
                            elif intent == "UNSUBSCRIBE":
                                lead.status = "UNSUBSCRIBED"
                            elif intent == "NOT_INTERESTED":
                                lead.status = "NOT_INTERESTED"
                        session.commit()
                    finally:
                        session.close()
                        
                    replies_found.append({
                        "from": sender_email,
                        "subject": decoded_subject,
                        "intent": intent
                    })
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"[InboxMonitor] Error checking inbox for {account_email}: {e}")
        
    return replies_found

def check_all_inboxes() -> List[Dict[str, Any]]:
    """Checks all 4 configured Gmail inboxes."""
    all_replies = []
    accounts = [
        (settings.GMAIL_ACCOUNT_1_USER, settings.GMAIL_ACCOUNT_1_PASS),
        (settings.GMAIL_ACCOUNT_2_USER, settings.GMAIL_ACCOUNT_2_PASS),
        (settings.GMAIL_ACCOUNT_3_USER, settings.GMAIL_ACCOUNT_3_PASS),
        (settings.GMAIL_ACCOUNT_4_USER, settings.GMAIL_ACCOUNT_4_PASS)
    ]
    for user, pwd in accounts:
        if user and pwd:
            replies = check_account_inbox(user, pwd)
            all_replies.extend(replies)
    return all_replies
