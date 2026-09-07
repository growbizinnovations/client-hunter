import smtplib
import ssl
import time
import random
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

def test_gmail_credentials(email_addr: str, app_pass: str) -> Tuple[bool, str]:
    """Tests live connection to both Gmail SMTP and IMAP."""
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(email_addr, app_pass)
        return True, "Gmail SMTP & Authentication Connected Successfully!"
    except Exception as e:
        return False, f"Authentication Failed: {str(e)}"

def send_single_email(sender_email: str, sender_password: str, recipient_email: str, subject: str, body_text: str, body_html: str = None) -> Tuple[bool, Optional[str]]:
    """Sends a single email using SMTP with TLS."""
    if settings.DRY_RUN:
        print(f"[DRY_RUN] Simulating email send from {sender_email} to {recipient_email}")
        print(f"  Subject: {subject}")
        return True, None
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.SENDER_NAME} <{sender_email}>"
        msg["To"] = recipient_email
        
        part1 = MIMEText(body_text, "plain", "utf-8")
        msg.attach(part1)
        
        if body_html:
            part2 = MIMEText(body_html, "html", "utf-8")
            msg.attach(part2)
            
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
            
        return True, None
    except Exception as e:
        err_msg = str(e)
        print(f"[Sender] Error sending email via {sender_email} to {recipient_email}: {err_msg}")
        return False, err_msg

def process_email_queue(max_batch_size: int = 10) -> int:
    """Processes queued emails using available accounts respecting warmup ramp-up limits."""
    account_mgr = GmailAccountManager()
    session = SessionLocal()
    sent_count = 0
    
    try:
        queued_campaigns = session.query(EmailCampaign).filter(EmailCampaign.status == "QUEUED").order_by(EmailCampaign.created_at.asc()).limit(max_batch_size).all()
        
        for camp in queued_campaigns:
            acc = account_mgr.get_available_account()
            if not acc:
                print(f"[Sender] Account has reached today's warmup cap. Pausing sends.")
                break
                
            print(f"[Sender] Dispatching email #{camp.id} to {camp.recipient_email} via {acc['user']} (Warmup Day {acc['warmup_day']} - Limit: {acc['daily_limit']})...")
            success, err = send_single_email(
                sender_email=acc["user"],
                sender_password=acc["pass"],
                recipient_email=camp.recipient_email,
                subject=camp.subject,
                body_text=camp.body_text,
                body_html=camp.body_html
            )
            
            if success:
                mark_email_sent(camp.id)
                increment_daily_sent_count(acc["user"])
                sent_count += 1
                
                delay = random.randint(3, 5) if settings.DRY_RUN else random.randint(settings.MIN_DELAY_BETWEEN_EMAILS_SEC, settings.MAX_DELAY_BETWEEN_EMAILS_SEC)
                print(f"  [+] Sent successfully! Waiting {delay}s before next send...")
                time.sleep(delay)
            else:
                camp.status = "FAILED"
                camp.error_message = err
                session.commit()
                
        return sent_count
    finally:
        session.close()
