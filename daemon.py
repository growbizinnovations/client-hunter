import time
import json
import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings
from database.db_manager import (
    init_db, get_next_city_to_scan, mark_city_scanned,
    get_leads_ready_for_pitch, queue_email, get_stats, SessionLocal
)
from database.models import Lead, WebsiteAudit, ContactInfo
from modules.discovery import discover_businesses_for_city
from modules.website_auditor import audit_website
from modules.email_extractor import harvest_contact_emails
from modules.ai_pitcher import generate_personalized_pitch
from modules.sender import process_email_queue, GmailAccountManager
from modules.inbox_monitor import check_all_inboxes
from modules.follow_up import check_and_queue_follow_ups

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def job_discover_and_audit():
    """Daily job: Picks the next US city (East to West), discovers leads, audits websites, extracts emails, and generates pitches."""
    logging.info("=== [DAEMON] Starting City Discovery & Website Audit Pipeline ===")
    
    city_obj = get_next_city_to_scan()
    if not city_obj:
        logging.warning("[DAEMON] No cities found in database.")
        return
        
    logging.info(f"[DAEMON] Active target city: {city_obj.city}, {city_obj.state} (Lon: {city_obj.lon})")
    
    # 1. Discover Businesses
    discovered = discover_businesses_for_city(city_obj.city, city_obj.state, max_leads_per_niche=4)
    
    # 2. Audit Websites for newly discovered or pending leads
    session = SessionLocal()
    try:
        pending_leads = session.query(Lead).filter(
            Lead.city == city_obj.city,
            Lead.state == city_obj.state,
            Lead.status == "DISCOVERED"
        ).all()
        
        for lead in pending_leads:
            logging.info(f"[DAEMON] Auditing: {lead.business_name} ({lead.website_url})")
            audit_res = audit_website(lead.id, lead.website_url)
            
            # If outdated, harvest contact emails
            if audit_res["is_outdated"]:
                logging.info(f"  -> Outdated website confirmed! Extracting contact emails...")
                emails = harvest_contact_emails(lead.id, lead.website_url, lead.domain)
                if not emails:
                    lead.status = "NO_EMAIL_FOUND"
                    session.commit()
            else:
                logging.info(f"  -> Modern website. Skipping outreach.")
                
        session.commit()
    finally:
        session.close()
        
    # 3. Generate Pitches & Queue Emails for Outdated leads with Emails
    ready_leads = get_leads_ready_for_pitch(limit=60)
    logging.info(f"[DAEMON] Found {len(ready_leads)} leads ready for personalized outreach pitch.")
    
    account_mgr = GmailAccountManager()
    
    for lead in ready_leads:
        contact = lead.contacts[0] if lead.contacts else None
        if not contact:
            continue
            
        issues = []
        if lead.audit and lead.audit.issues_json:
            try:
                issues = json.loads(lead.audit.issues_json)
            except Exception:
                issues = []
                
        # Generate personalized pitch via Gemini AI
        pitch = generate_personalized_pitch(
            business_name=lead.business_name,
            city=lead.city,
            state=lead.state,
            domain=lead.domain,
            niche=lead.niche,
            issues=issues
        )
        
        # Determine sender account
        acc = account_mgr.get_available_account()
        sender_email = acc["user"] if acc else "default@outreach.local"
        
        queue_email(
            lead_id=lead.id,
            recipient_email=contact.email,
            sender_account=sender_email,
            subject=pitch["subject"],
            body_text=pitch["body_text"],
            body_html=None,
            email_type="INITIAL_OUTREACH"
        )
        logging.info(f"  [+] Queued personalized email for {lead.business_name} <{contact.email}>")
        
    # Mark city as scanned
    mark_city_scanned(city_obj.id)
    logging.info(f"=== [DAEMON] Completed pipeline for {city_obj.city}, {city_obj.state} ===")

def job_send_queued_emails():
    """Periodic job: Dispatches queued emails throughout the day respecting rate limits."""
    logging.info("[DAEMON] Running email queue dispatcher...")
    sent = process_email_queue(max_batch_size=5)
    logging.info(f"[DAEMON] Dispatched {sent} emails in this batch.")

def job_monitor_inbox():
    """Periodic job: Checks all 4 Gmail inboxes for responses and auto-responds."""
    logging.info("[DAEMON] Checking inboxes for replies...")
    replies = check_all_inboxes()
    if replies:
        logging.info(f"[DAEMON] Processed {len(replies)} new replies.")

def job_check_follow_ups():
    """Daily job: Queues follow-ups for non-responsive leads."""
    logging.info("[DAEMON] Checking follow-up eligibility...")
    queued = check_and_queue_follow_ups()
    logging.info(f"[DAEMON] Queued {queued} follow-up emails.")

def start_daemon():
    """Starts the 24/7 background scheduler."""
    init_db()
    
    scheduler = BlockingScheduler()
    
    # 1. Discover & Audit new city twice a day or every 12 hours
    scheduler.add_job(job_discover_and_audit, IntervalTrigger(hours=12), id="job_discovery", next_run_time=datetime.now())
    
    # 2. Dispatch queued emails every 15 minutes
    scheduler.add_job(job_send_queued_emails, IntervalTrigger(minutes=15), id="job_sender", next_run_time=datetime.now())
    
    # 3. Monitor inboxes every 10 minutes
    scheduler.add_job(job_monitor_inbox, IntervalTrigger(minutes=10), id="job_inbox", next_run_time=datetime.now())
    
    # 4. Check follow-ups once a day at 10:00 AM
    scheduler.add_job(job_check_follow_ups, CronTrigger(hour=10, minute=0), id="job_followup")
    
    logging.info("================================================================")
    logging.info(" 🚀 24/7 AUTONOMOUS COLD OUTREACH AGENT RUNNING")
    logging.info(" 4 Gmail Accounts | 15 emails/acc/day | 60 total/day")
    logging.info(f" Mode: {'DRY_RUN (Simulated)' if settings.DRY_RUN else 'LIVE SENDING'}")
    logging.info("================================================================")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("[DAEMON] Agent stopped gracefully.")

if __name__ == "__main__":
    start_daemon()
