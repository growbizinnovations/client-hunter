import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import time
import json
import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from settings import settings
from db_manager import (
    init_db, get_next_city_to_scan, mark_city_scanned,
    get_leads_ready_for_pitch, queue_email, get_stats, SessionLocal
)
from models import Lead, WebsiteAudit, ContactInfo
from discovery import discover_businesses_for_city, search_custom_niche_in_city
from website_auditor import audit_website
from email_extractor import harvest_contact_emails
from ai_pitcher import generate_personalized_pitch
from sender import process_email_queue, GmailAccountManager
from inbox_monitor import check_all_inboxes
from follow_up import check_and_queue_follow_ups

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SCAN_PROGRESS = {
    "is_scanning": False,
    "current_city": "",
    "current_niche": "",
    "stage": "Idle",
    "step": 0,
    "total_steps": 4,
    "pct": 0,
    "leads_found": 0,
    "audited_count": 0,
    "outdated_count": 0,
    "emails_found": 0,
    "pitches_queued": 0,
    "log_message": "Ready to scan"
}

def update_scan_progress(pct=None, stage=None, log=None, leads=None, audited=None, outdated=None, emails=None, pitches=None, niche=None, city=None):
    if pct is not None:
        SCAN_PROGRESS["pct"] = min(100, max(0, pct))
    if stage is not None:
        SCAN_PROGRESS["stage"] = stage
    if log is not None:
        SCAN_PROGRESS["log_message"] = log
    if leads is not None:
        SCAN_PROGRESS["leads_found"] = leads
    if audited is not None:
        SCAN_PROGRESS["audited_count"] = audited
    if outdated is not None:
        SCAN_PROGRESS["outdated_count"] = outdated
    if emails is not None:
        SCAN_PROGRESS["emails_found"] = emails
    if pitches is not None:
        SCAN_PROGRESS["pitches_queued"] = pitches
    if niche is not None:
        SCAN_PROGRESS["current_niche"] = niche
    if city is not None:
        SCAN_PROGRESS["current_city"] = city

def job_discover_and_audit():
    """Daily job: Picks the next US city (East to West), discovers leads, audits websites, extracts emails, and generates pitches."""
    global SCAN_PROGRESS
    SCAN_PROGRESS["is_scanning"] = True
    SCAN_PROGRESS["pct"] = 5
    SCAN_PROGRESS["leads_found"] = 0
    SCAN_PROGRESS["audited_count"] = 0
    SCAN_PROGRESS["outdated_count"] = 0
    SCAN_PROGRESS["emails_found"] = 0
    SCAN_PROGRESS["pitches_queued"] = 0
    SCAN_PROGRESS["current_niche"] = "Initializing"
    
    logging.info("=== [DAEMON] Starting City Discovery & Website Audit Pipeline ===")
    
    try:
        city_obj = get_next_city_to_scan()
        if not city_obj:
            logging.warning("[DAEMON] No cities found in database.")
            update_scan_progress(pct=100, stage="Completed", log="No pending cities in database.")
            SCAN_PROGRESS["is_scanning"] = False
            return
            
        city_name = f"{city_obj.city}, {city_obj.state}"
        SCAN_PROGRESS["current_city"] = city_name
        update_scan_progress(pct=10, stage=f"Step 1/4: Discovering businesses in {city_name}", log=f"Searching local high-ticket niches in {city_name} (East-to-West Route)...", city=city_name)
        logging.info(f"[DAEMON] Active target city: {city_obj.city}, {city_obj.state} (Lon: {city_obj.lon})")
        
        # 1. Discover Businesses with granular niche and total businesses count
        def on_search_progress(c_city, c_state, c_niche, cat_num, total_n, found_cnt, msg):
            calc_pct = 10 + int((cat_num / max(1, total_n)) * 25)
            update_scan_progress(
                pct=calc_pct,
                niche=f"Category {cat_num}/{total_n}: {c_niche}",
                leads=found_cnt,
                log=msg,
                stage=f"Step 1/4: Category {cat_num} of {total_n} ({c_niche}) in {c_city}, {c_state}"
            )
            
        discovered = discover_businesses_for_city(city_obj.city, city_obj.state, max_leads_per_niche=20, progress_callback=on_search_progress)
        
        # 2. Audit Websites for newly discovered or pending leads
        session = SessionLocal()
        outdated_leads = []
        try:
            pending_leads = session.query(Lead).filter(
                Lead.city == city_obj.city,
                Lead.state == city_obj.state,
                Lead.status == "DISCOVERED"
            ).all()
            
            total_pending = len(pending_leads)
            update_scan_progress(pct=35, stage=f"Step 2/4: Auditing {total_pending} websites in {city_name}", leads=total_pending, log=f"Found {total_pending} business targets. Starting website health audits...")
            
            audited_cnt = 0
            outdated_cnt = 0
            
            for idx, lead in enumerate(pending_leads):
                audited_cnt += 1
                curr_pct = 35 + int((idx / max(1, total_pending)) * 30)
                update_scan_progress(pct=curr_pct, audited=audited_cnt, log=f"Auditing [{idx+1}/{total_pending}]: {lead.business_name} ({lead.domain})...")
                logging.info(f"[DAEMON] Auditing: {lead.business_name} ({lead.website_url})")
                audit_res = audit_website(lead.id, lead.website_url)
                
                if audit_res["is_outdated"]:
                    outdated_cnt += 1
                    outdated_leads.append(lead)
                    update_scan_progress(outdated=outdated_cnt, log=f"⚠️ Outdated site detected: {lead.business_name} (Score: {audit_res['outdated_score']}/100)")
                    logging.info(f"  -> Outdated website confirmed! Extracting contact emails...")
                    emails = harvest_contact_emails(lead.id, lead.website_url, lead.domain)
                    if emails:
                        update_scan_progress(emails=SCAN_PROGRESS["emails_found"] + len(emails))
                    else:
                        lead.status = "NO_EMAIL_FOUND"
                        session.commit()
                else:
                    logging.info(f"  -> Modern website. Skipping outreach.")
                    
            session.commit()
        finally:
            session.close()
            
        # 3. Generate Pitches & Queue Emails for Outdated leads with Emails
        update_scan_progress(pct=75, stage=f"Step 3/4: Extracting emails & crafting pitches", log=f"Generating personalized $500 redesign demo pitches...")
        ready_leads = get_leads_ready_for_pitch(limit=60)
        logging.info(f"[DAEMON] Found {len(ready_leads)} leads ready for personalized outreach pitch.")
        
        account_mgr = GmailAccountManager()
        pitches_cnt = 0
        
        for idx, lead in enumerate(ready_leads):
            contact = lead.contacts[0] if lead.contacts else None
            if not contact:
                continue
                
            issues = []
            if lead.audit and lead.audit.issues_json:
                try:
                    issues = json.loads(lead.audit.issues_json)
                except Exception:
                    issues = []
                    
            curr_pct = 75 + int((idx / max(1, len(ready_leads))) * 20)
            update_scan_progress(pct=curr_pct, log=f"AI Pitch generation for {lead.business_name}...")
            
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
            pitches_cnt += 1
            update_scan_progress(pitches=pitches_cnt, log=f"✅ Queued demo email for {lead.business_name} <{contact.email}>")
            logging.info(f"  [+] Queued personalized email for {lead.business_name} <{contact.email}>")
            
        # Mark city as scanned
        mark_city_scanned(city_obj.id)
        update_scan_progress(pct=100, stage="Scan Complete!", log=f"Successfully scanned {city_name}! Leads and campaigns are populated.")
        logging.info(f"=== [DAEMON] Completed pipeline for {city_obj.city}, {city_obj.state} ===")
    except Exception as e:
        logging.error(f"[DAEMON] Error during city scan: {e}")
        update_scan_progress(pct=100, stage="Error", log=f"Scan error: {str(e)}")
    finally:
        SCAN_PROGRESS["is_scanning"] = False

def run_on_demand_pipeline(niche: str, location: str = ""):
    """Executes on-demand Google Maps & Web discovery + website health audit + email extraction for any natural search query."""
    global SCAN_PROGRESS
    full_target = f"{niche} in {location}".strip() if (location and location.strip()) else niche.strip()
    SCAN_PROGRESS["is_scanning"] = True
    SCAN_PROGRESS["pct"] = 5
    SCAN_PROGRESS["current_city"] = location if location else "Google Maps"
    SCAN_PROGRESS["current_niche"] = niche
    SCAN_PROGRESS["leads_found"] = 0
    SCAN_PROGRESS["audited_count"] = 0
    SCAN_PROGRESS["outdated_count"] = 0
    SCAN_PROGRESS["emails_found"] = 0
    SCAN_PROGRESS["pitches_queued"] = 0
    SCAN_PROGRESS["stage"] = f"Searching Google Maps for '{full_target}'..."
    SCAN_PROGRESS["log_message"] = f"Starting deep scan across all result pages..."
    
    try:
        def on_search(pct, msg, cnt):
            update_scan_progress(pct=pct, log=msg, leads=cnt)
            
        discovered = search_custom_niche_in_city(niche, location, max_results=45, progress_callback=on_search)
        total_discovered = len(discovered)
        update_scan_progress(pct=45, stage=f"Auditing {total_discovered} websites for '{full_target}'", leads=total_discovered, log=f"Discovered {total_discovered} businesses. Auditing website design quality...")
        
        session = SessionLocal()
        outdated_cnt = 0
        audited_cnt = 0
        
        try:
            for idx, item in enumerate(discovered):
                lead = session.query(Lead).filter(Lead.id == item["id"]).first()
                if not lead:
                    continue
                audited_cnt += 1
                curr_pct = 45 + int((idx / max(1, total_discovered)) * 30)
                update_scan_progress(pct=curr_pct, audited=audited_cnt, log=f"Auditing [{idx+1}/{total_discovered}]: {lead.business_name} ({lead.domain})...")
                
                audit_res = audit_website(lead.id, lead.website_url)
                if audit_res["is_outdated"]:
                    outdated_cnt += 1
                    update_scan_progress(outdated=outdated_cnt, log=f"⚠️ Outdated website confirmed: {lead.business_name} (Score: {audit_res['outdated_score']}/100)")
                    emails = harvest_contact_emails(lead.id, lead.website_url, lead.domain)
                    if emails:
                        update_scan_progress(emails=SCAN_PROGRESS["emails_found"] + len(emails))
                    else:
                        lead.status = "NO_EMAIL_FOUND"
                        session.commit()
                else:
                    logging.info(f"  -> Modern website: {lead.business_name}")
            session.commit()
        finally:
            session.close()
            
        # Generate pitches for ready leads
        update_scan_progress(pct=80, stage=f"Generating pitches for outdated websites", log=f"Crafting personalized $500 redesign demo offers...")
        ready_leads = get_leads_ready_for_pitch(limit=40)
        pitches_cnt = 0
        for idx, lead in enumerate(ready_leads):
            contact = lead.contacts[0] if lead.contacts else None
            if not contact:
                continue
            curr_pct = 80 + int((idx / max(1, len(ready_leads))) * 18)
            update_scan_progress(pct=curr_pct, log=f"AI Pitch generation for {lead.business_name}...")
            pitch = generate_personalized_pitch(
                business_name=lead.business_name,
                domain=lead.domain,
                niche=lead.niche,
                city=lead.city,
                state=lead.state,
                issues=[] if not (lead.audit and lead.audit.issues_json) else json.loads(lead.audit.issues_json),
                offer_price=settings.REDESIGN_OFFER_PRICE,
                sender_name=settings.SENDER_NAME
            )
            queue_email(
                lead_id=lead.id,
                recipient_email=contact.email,
                sender_account=settings.GMAIL_ACCOUNT_1_USER,
                subject=pitch["subject"],
                body_text=pitch["body_text"],
                body_html=pitch.get("body_html"),
                email_type="INITIAL_OUTREACH"
            )
            pitches_cnt += 1
            update_scan_progress(pitches=pitches_cnt, log=f"✅ Queued pitch for {lead.business_name} <{contact.email}>")
            
        update_scan_progress(pct=100, stage="Search & Audit Completed!", log=f"Completed '{niche}' search in {location}! Discovered {total_discovered} businesses, {outdated_cnt} outdated targets.")
    except Exception as e:
        logging.error(f"[On-Demand Search] Error: {e}")
        update_scan_progress(pct=100, stage="Search Error", log=f"Error: {str(e)}")
    finally:
        SCAN_PROGRESS["is_scanning"] = False

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
