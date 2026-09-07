import smtplib
import ssl
import time
import random
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from settings import settings
from db_manager import (
    get_account_warmup_status, increment_daily_sent_count, mark_email_sent, SessionLocal
)
from models import EmailCampaign

class GmailAccountManager:
    def __init__(self):
        self.accounts = []
        self._load_accounts()
        
    def _load_accounts(self):
        accs = [
            {"user": settings.GMAIL_ACCOUNT_1_USER, "pass": settings.GMAIL_ACCOUNT_1_PASS, "id": 1},
            {"user": settings.GMAIL_ACCOUNT_2_USER, "pass": settings.GMAIL_ACCOUNT_2_PASS, "id": 2},
            {"user": settings.GMAIL_ACCOUNT_3_USER, "pass": settings.GMAIL_ACCOUNT_3_PASS, "id": 3},
            {"user": settings.GMAIL_ACCOUNT_4_USER, "pass": settings.GMAIL_ACCOUNT_4_PASS, "id": 4},
        ]
        self.accounts = [a for a in accs if a["user"] and a["pass"]]
        if not self.accounts:
            # Fallback mock for UI / DRY_RUN
            self.accounts = [
                {"user": "primary_account@gmail.com", "pass": "mock_password", "id": 1}
            ]
            
    def get_available_account(self) -> Optional[Dict[str, Any]]:
        """Returns the next available Gmail account that has not exceeded today's warmup cap."""
        self._load_accounts()
        for acc in self.accounts:
            warmup = get_account_warmup_status(acc["user"])
            if warmup["sent_today"] < warmup["daily_limit"]:
                return {**acc, **warmup}
        return None

    def get_all_accounts_status(self) -> List[Dict[str, Any]]:
        self._load_accounts()
        statuses = []
        for acc in self.accounts:
            warmup = get_account_warmup_status(acc["user"])
            statuses.append(warmup)
        return statuses

import socket

def _get_smtp_connection(sender_email: str, sender_password: str, timeout: int = 15):
    """Creates a robust Gmail SMTP connection supporting SSL Port 465 and TLS Port 587."""
    try:
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=timeout)
        server.login(sender_email, sender_password)
        return server
    except Exception as e1:
        try:
            context = ssl.create_default_context()
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=timeout)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(sender_email, sender_password)
            return server
        except Exception as e2:
            raise Exception(f"Connection failed (SSL 465: {e1} | TLS 587: {e2})")

def send_via_resend(api_key: str, from_name: str, from_email: str, recipient_email: str, subject: str, body_text: str, body_html: str = None) -> Tuple[bool, Optional[str]]:
    """Sends email via Resend HTTPS API (Port 443 - 100% bypasses cloud SMTP port blocks)."""
    try:
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json"
        }
        sender = f"{from_name} <onboarding@resend.dev>" if "gmail.com" in from_email or not from_email else f"{from_name} <{from_email}>"
        payload = {
            "from": sender,
            "to": [recipient_email],
            "subject": subject,
            "text": body_text,
            "html": body_html if body_html else body_text.replace("\n", "<br>")
        }
        res = requests.post("https://api.resend.com/emails", headers=headers, json=payload, timeout=15)
        if res.status_code in [200, 201]:
            return True, None
        return False, f"Resend API Error ({res.status_code}): {res.text}"
    except Exception as e:
        return False, f"Resend API Exception: {e}"

def send_via_brevo(api_key: str, from_name: str, from_email: str, recipient_email: str, subject: str, body_text: str, body_html: str = None) -> Tuple[bool, Optional[str]]:
    """Sends email via Brevo HTTPS API (Port 443 - 100% bypasses cloud SMTP port blocks)."""
    try:
        headers = {
            "api-key": api_key.strip(),
            "Content-Type": "application/json"
        }
        payload = {
            "sender": {"name": from_name, "email": from_email},
            "to": [{"email": recipient_email}],
            "subject": subject,
            "textContent": body_text,
            "htmlContent": body_html if body_html else body_text.replace("\n", "<br>")
        }
        res = requests.post("https://api.brevo.com/v3/smtp/email", headers=headers, json=payload, timeout=15)
        if res.status_code in [200, 201]:
            return True, None
        return False, f"Brevo API Error ({res.status_code}): {res.text}"
    except Exception as e:
        return False, f"Brevo API Exception: {e}"

def test_gmail_credentials(email_addr: str, app_pass: str) -> Tuple[bool, str]:
    """Tests live connection to Gmail SMTP."""
    clean_pass = app_pass.replace(" ", "")
    try:
        server = _get_smtp_connection(email_addr, clean_pass, timeout=12)
        server.quit()
        return True, "Gmail SMTP Connected & Authenticated Successfully!"
    except Exception as e:
        return False, f"Authentication Failed: {str(e)}"

def send_single_email(sender_email: str, sender_password: str, recipient_email: str, subject: str, body_text: str, body_html: str = None, campaign_id: int = None) -> Tuple[bool, Optional[str]]:
    """Sends a single email using HTTPS API (Resend/Brevo) or robust Gmail SMTP."""
    if settings.DRY_RUN:
        print(f"[DRY_RUN] Simulating email send from {sender_email} to {recipient_email}")
        print(f"  Subject: {subject}")
        return True, None

    # 1. Check for HTTPS API Keys (Bypasses Render / Cloud SMTP Blocks)
    if settings.RESEND_API_KEY:
        print(f"[Sender] Dispatching via Resend HTTPS API (Port 443)...")
        return send_via_resend(settings.RESEND_API_KEY, settings.SENDER_NAME, sender_email, recipient_email, subject, body_text, body_html)
        
    if settings.BREVO_API_KEY:
        print(f"[Sender] Dispatching via Brevo HTTPS API (Port 443)...")
        return send_via_brevo(settings.BREVO_API_KEY, settings.SENDER_NAME, sender_email, recipient_email, subject, body_text, body_html)
        
    # 2. Direct Gmail SMTP
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.SENDER_NAME} <{sender_email}>"
        msg["To"] = recipient_email
        
        part1 = MIMEText(body_text, "plain", "utf-8")
        msg.attach(part1)
        
        # Build HTML with open tracking pixel
        pixel_tag = f'<img src="https://client-hunter-1.onrender.com/track/open/{campaign_id}" width="1" height="1" style="display:none;" />' if campaign_id else ''
        html_content = body_html if body_html else f"""<div style="font-family: sans-serif; font-size: 14px; line-height: 1.6; color: #222;">
{body_text.replace(chr(10), '<br>')}
{pixel_tag}
</div>"""
        part2 = MIMEText(html_content, "html", "utf-8")
        msg.attach(part2)
            
        clean_pass = sender_password.replace(" ", "")
        server = _get_smtp_connection(sender_email, clean_pass, timeout=15)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        return True, None
    except Exception as e:
        err_msg = str(e)
        print(f"[Sender] Error sending email via {sender_email} to {recipient_email}: {err_msg}")
        if "Network is unreachable" in err_msg or "101" in err_msg or "timed out" in err_msg:
            err_msg = "Render Cloud Firewall blocks direct SMTP ports. Please click 'Open in Gmail Composer' below to send with 1 click directly from your Gmail, or add a free Resend/Brevo API key in Settings."
        return False, err_msg

def send_campaign_now(campaign_id: int) -> Tuple[bool, str]:
    """Immediately sends a single campaign email by ID and updates its status in DB."""
    session = SessionLocal()
    try:
        camp = session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
        if not camp:
            return False, f"Campaign #{campaign_id} not found."
            
        sender_usr = settings.GMAIL_ACCOUNT_1_USER
        sender_pwd = settings.GMAIL_ACCOUNT_1_PASS
        
        if not sender_usr or not sender_pwd:
            return False, "Gmail account credentials not configured in Settings."
            
        success, err = send_single_email(
            sender_email=sender_usr,
            sender_password=sender_pwd,
            recipient_email=camp.recipient_email,
            subject=camp.subject,
            body_text=camp.body_text,
            body_html=camp.body_html,
            campaign_id=camp.id
        )
        
        if success:
            mark_email_sent(camp.id)
            increment_daily_sent_count(sender_usr)
            return True, f"Email successfully sent to {camp.recipient_email}!"
        else:
            camp.status = "FAILED"
            camp.error_message = err
            session.commit()
            return False, f"Send failed: {err}"
    finally:
        session.close()

def process_email_queue(max_batch_size: int = 10, include_failed: bool = True) -> int:
    """Processes queued (and optionally failed) emails using available accounts."""
    account_mgr = GmailAccountManager()
    session = SessionLocal()
    sent_count = 0
    
    try:
        statuses = ["QUEUED"]
        if include_failed:
            statuses.append("FAILED")
            
        queued_campaigns = session.query(EmailCampaign).filter(
            EmailCampaign.status.in_(statuses)
        ).order_by(EmailCampaign.created_at.asc()).limit(max_batch_size).all()
        
        for camp in queued_campaigns:
            acc = account_mgr.get_available_account()
            if not acc:
                print(f"[Sender] Account has reached today's warmup cap or not configured. Pausing sends.")
                break
                
            sender_usr = acc["user"] if acc.get("user") and acc.get("user") != "primary_account@gmail.com" else settings.GMAIL_ACCOUNT_1_USER
            sender_pwd = acc["pass"] if acc.get("pass") and acc.get("pass") != "mock_password" else settings.GMAIL_ACCOUNT_1_PASS
            
            if not sender_usr or not sender_pwd:
                camp.status = "FAILED"
                camp.error_message = "Gmail account credentials not configured in Settings."
                session.commit()
                continue
                
            print(f"[Sender] Dispatching email #{camp.id} to {camp.recipient_email} via {sender_usr} (Warmup Day {acc.get('warmup_day', 1)} - Limit: {acc.get('daily_limit', 5)})...")
            success, err = send_single_email(
                sender_email=sender_usr,
                sender_password=sender_pwd,
                recipient_email=camp.recipient_email,
                subject=camp.subject,
                body_text=camp.body_text,
                body_html=camp.body_html,
                campaign_id=camp.id
            )
            
            if success:
                mark_email_sent(camp.id)
                increment_daily_sent_count(sender_usr)
                sent_count += 1
                
                delay = random.randint(2, 4) if settings.DRY_RUN else random.randint(settings.MIN_DELAY_BETWEEN_EMAILS_SEC, settings.MAX_DELAY_BETWEEN_EMAILS_SEC)
                print(f"  [+] Sent successfully! Waiting {delay}s before next send...")
                time.sleep(delay)
            else:
                camp.status = "FAILED"
                camp.error_message = err
                session.commit()
                
        return sent_count
    finally:
        session.close()
