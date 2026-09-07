import os
import json
import sys
import threading
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
import uvicorn

from settings import settings
from db_manager import (
    init_db, get_stats, get_account_warmup_status, SessionLocal,
    delete_lead, cleanup_modern_leads, clear_all_leads_data, set_active_target_city,
    increment_daily_sent_count, mark_email_sent
)
from models import CityProgress, Lead, WebsiteAudit, ContactInfo, EmailCampaign, InboxMessage, DailySendLog
from sender import GmailAccountManager, test_gmail_credentials, process_email_queue, send_single_email, send_campaign_now
from ai_pitcher import generate_personalized_pitch, clean_prospect_name
from inbox_monitor import check_all_inboxes
from daemon import job_discover_and_audit, job_send_queued_emails, job_monitor_inbox, job_check_follow_ups

init_db()

app = FastAPI(title="Client Hunter 24/7 Web Agent", version="2.0.0")

DAEMON_RUNNING = False
DAEMON_THREAD = None

def daemon_worker_loop():
    global DAEMON_RUNNING
    print("[Web Daemon] 24/7 Background autonomous worker started.", flush=True)
    scan_timer = 0
    while DAEMON_RUNNING:
        try:
            if scan_timer <= 0:
                print("[Web Daemon] Running scheduled city scan...", flush=True)
                job_discover_and_audit()
                scan_timer = 43200
            process_email_queue(max_batch_size=5)
            check_all_inboxes()
            job_check_follow_ups()
        except Exception as e:
            print(f"[Web Daemon] Error in background cycle: {e}", flush=True)
        for _ in range(60):
            if not DAEMON_RUNNING:
                break
            time.sleep(1)
        scan_timer -= 60

class SettingsUpdateRequest(BaseModel):
    gmail_user: str
    gmail_pass: str
    sender_name: Optional[str] = "Tushar"
    gemini_key: Optional[str] = ""
    resend_key: Optional[str] = ""
    brevo_key: Optional[str] = ""
    dry_run: Optional[bool] = False

class TestEmailRequest(BaseModel):
    gmail_user: str
    gmail_pass: str

@app.get("/api/stats")
def api_get_stats():
    stats = get_stats()
    account_mgr = GmailAccountManager()
    accounts = account_mgr.get_all_accounts_status()
    return {
        "stats": stats,
        "accounts": accounts,
        "daemon_running": DAEMON_RUNNING,
        "dry_run": settings.DRY_RUN
    }

from sqlalchemy import func
from db_manager import (
    init_db, get_stats, get_account_warmup_status, SessionLocal,
    delete_lead, cleanup_modern_leads, clear_all_leads_data, set_active_target_city
)

class SetActiveCityRequest(BaseModel):
    city: str
    state: str

@app.get("/api/leads")
def api_get_leads(limit: int = 200, status_filter: str = "ALL", sort_by: str = "worst_first", niche: str = "ALL"):
    session = SessionLocal()
    try:
        query = session.query(Lead).outerjoin(WebsiteAudit)
        
        if status_filter == "OUTDATED":
            query = query.filter(Lead.status.in_(["AUDITED_OUTDATED", "EMAIL_FOUND", "EMAIL_QUEUED", "EMAIL_SENT", "FOLLOW_UP_1", "FOLLOW_UP_2", "REPLIED"]))
        elif status_filter == "MODERN":
            query = query.filter(Lead.status == "AUDITED_MODERN")
        elif status_filter == "EMAIL_FOUND":
            query = query.filter(Lead.status.in_(["EMAIL_FOUND", "EMAIL_QUEUED", "EMAIL_SENT", "FOLLOW_UP_1", "FOLLOW_UP_2", "REPLIED"]))
            
        if niche != "ALL" and niche.strip():
            query = query.filter(func.lower(Lead.niche).contains(niche.strip().lower()))
            
        if sort_by == "worst_first":
            query = query.order_by(WebsiteAudit.outdated_score.desc(), Lead.id.desc())
        elif sort_by == "best_first":
            query = query.order_by(WebsiteAudit.outdated_score.asc(), Lead.id.desc())
        elif sort_by == "name_asc":
            query = query.order_by(Lead.business_name.asc())
        else: # recent
            query = query.order_by(Lead.id.desc())
            
        leads = query.limit(limit).all()
        data = []
        for l in leads:
            issues = []
            if l.audit and l.audit.issues_json:
                try:
                    issues = json.loads(l.audit.issues_json)
                except Exception:
                    issues = []
            clean_name = clean_prospect_name(l.business_name, l.domain, l.niche)
            data.append({
                "id": l.id,
                "business_name": clean_name,
                "domain": l.domain,
                "website_url": l.website_url,
                "city": l.city,
                "state": l.state,
                "niche": l.niche,
                "status": l.status,
                "outdated_score": l.audit.outdated_score if l.audit else 0,
                "copyright_year": l.audit.copyright_year if l.audit else None,
                "is_outdated": l.audit.is_outdated if l.audit else False,
                "issues": issues,
                "emails": [c.email for c in l.contacts],
                "created_at": l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else None
            })
        return data
    except Exception as e:
        print(f"[API Error] /api/leads error: {e}", flush=True)
        return []
    finally:
        session.close()

@app.delete("/api/leads/{lead_id}")
def api_delete_lead(lead_id: int):
    success = delete_lead(lead_id)
    return {"success": success, "message": f"Lead #{lead_id} removed."}

@app.post("/api/leads/cleanup-modern")
def api_cleanup_modern():
    count = cleanup_modern_leads()
    return {"success": True, "count": count, "message": f"Removed {count} modern/good websites from list."}

@app.post("/api/leads/clear-all")
def api_clear_all_leads():
    success = clear_all_leads_data()
    return {"success": success, "message": "All discovered leads and campaigns cleared successfully."}

@app.post("/api/cities/set-active")
def api_set_active_city(req: SetActiveCityRequest):
    success = set_active_target_city(req.city, req.state)
    return {"success": success, "message": f"Active target city locked to {req.city}, {req.state}."}

class SendCustomEmailRequest(BaseModel):
    recipient_email: str
    subject: str
    body_text: str

@app.get("/api/leads/{lead_id}/draft-pitch")
def api_get_lead_draft_pitch(lead_id: int):
    session = SessionLocal()
    try:
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return JSONResponse(status_code=404, content={"success": False, "message": "Lead not found"})
        
        issues = []
        if lead.audit and lead.audit.issues_json:
            try:
                issues = json.loads(lead.audit.issues_json)
            except Exception:
                issues = []
        
        clean_name = clean_prospect_name(lead.business_name, lead.domain, lead.niche)
        
        pitch = generate_personalized_pitch(
            business_name=clean_name,
            city=lead.city,
            state=lead.state,
            domain=lead.domain,
            niche=lead.niche,
            issues=issues
        )
        
        recipient_email = lead.contacts[0].email if lead.contacts else ""
        
        return {
            "success": True,
            "lead_id": lead.id,
            "business_name": clean_name,
            "domain": lead.domain,
            "city": lead.city,
            "state": lead.state,
            "recipient_email": recipient_email,
            "emails": [c.email for c in lead.contacts],
            "subject": pitch.get("subject", f"Quick question regarding {lead.domain}"),
            "body_text": pitch.get("body_text", "")
        }
    finally:
        session.close()

@app.post("/api/leads/{lead_id}/mark-sent")
def api_mark_custom_email_sent(lead_id: int, req: SendCustomEmailRequest):
    session = SessionLocal()
    try:
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return {"success": False, "message": f"Lead #{lead_id} not found."}
            
        recipient = req.recipient_email.strip()
        sender_usr = settings.GMAIL_ACCOUNT_1_USER or "tusharkumarbusinessgrowth@gmail.com"
        
        camp = session.query(EmailCampaign).filter(
            EmailCampaign.lead_id == lead.id,
            EmailCampaign.recipient_email == recipient
        ).first()
        
        if not camp:
            camp = EmailCampaign(
                lead_id=lead.id,
                recipient_email=recipient,
                sender_account=sender_usr,
                subject=req.subject.strip(),
                body_text=req.body_text.strip(),
                email_type="INITIAL",
                status="SENT",
                sent_at=datetime.utcnow()
            )
            session.add(camp)
        else:
            camp.subject = req.subject.strip()
            camp.body_text = req.body_text.strip()
            camp.sender_account = sender_usr
            camp.status = "SENT"
            camp.sent_at = datetime.utcnow()
            
        lead.status = "EMAIL_SENT"
        increment_daily_sent_count(sender_usr)
        session.commit()
        return {"success": True, "message": f"Lead #{lead.id} successfully marked as SENT in campaign tracker!"}
    finally:
        session.close()

@app.post("/api/leads/{lead_id}/send-custom-email")
def api_send_custom_email(lead_id: int, req: SendCustomEmailRequest):
    session = SessionLocal()
    try:
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return {"success": False, "message": f"Lead #{lead_id} not found."}
            
        recipient = req.recipient_email.strip()
        if not recipient or "@" not in recipient:
            return {"success": False, "message": "Please provide a valid recipient email address."}
            
        sender_usr = settings.GMAIL_ACCOUNT_1_USER
        sender_pwd = settings.GMAIL_ACCOUNT_1_PASS
        if not sender_usr or not sender_pwd:
            return {"success": False, "message": "Gmail account not configured in Settings. Please add your Gmail & App Password in the Settings tab."}
            
        camp = session.query(EmailCampaign).filter(
            EmailCampaign.lead_id == lead.id,
            EmailCampaign.recipient_email == recipient
        ).first()
        
        if not camp:
            camp = EmailCampaign(
                lead_id=lead.id,
                recipient_email=recipient,
                sender_account=sender_usr,
                subject=req.subject.strip(),
                body_text=req.body_text.strip(),
                email_type="INITIAL",
                status="QUEUED"
            )
            session.add(camp)
            session.commit()
            session.refresh(camp)
        else:
            camp.subject = req.subject.strip()
            camp.body_text = req.body_text.strip()
            camp.sender_account = sender_usr
            camp.status = "QUEUED"
            session.commit()

        success, err = send_single_email(
            sender_email=sender_usr,
            sender_password=sender_pwd,
            recipient_email=recipient,
            subject=req.subject.strip(),
            body_text=req.body_text.strip(),
            campaign_id=camp.id
        )
        
        if success:
            mark_email_sent(camp.id)
            increment_daily_sent_count(sender_usr)
            lead.status = "EMAIL_SENT"
            session.commit()
            return {"success": True, "message": f"Outreach email successfully sent to {recipient} via Gmail!"}
        else:
            camp.status = "FAILED"
            camp.error_message = err
            session.commit()
            return {"success": False, "message": f"Send failed: {err}"}
    finally:
        session.close()

PIXEL_PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'

@app.get("/track/open/{campaign_id}")
def api_track_open(campaign_id: int):
    session = SessionLocal()
    try:
        camp = session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
        if camp:
            camp.is_opened = True
            if not camp.opened_at:
                camp.opened_at = datetime.utcnow()
            session.commit()
    except Exception as e:
        print(f"[Open Tracker] Error: {e}")
    finally:
        session.close()
    return Response(content=PIXEL_PNG, media_type="image/png")

@app.get("/api/campaigns")
def api_get_campaigns(limit: int = 50):
    session = SessionLocal()
    try:
        campaigns = session.query(EmailCampaign).order_by(EmailCampaign.id.desc()).limit(limit).all()
        data = []
        for c in campaigns:
            lead_name = c.lead.business_name if c.lead else "Unknown"
            data.append({
                "id": c.id,
                "business_name": lead_name,
                "recipient_email": c.recipient_email,
                "sender_account": c.sender_account,
                "subject": c.subject,
                "body_text": c.body_text,
                "status": c.status,
                "is_opened": getattr(c, "is_opened", False),
                "opened_at": c.opened_at.strftime("%Y-%m-%d %H:%M") if getattr(c, "opened_at", None) else None,
                "email_type": c.email_type,
                "sent_at": c.sent_at.strftime("%Y-%m-%d %H:%M") if c.sent_at else None,
                "error_message": c.error_message,
                "created_at": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else None
            })
        return data
    finally:
        session.close()

@app.get("/api/inbox")
def api_get_inbox(limit: int = 50):
    session = SessionLocal()
    try:
        messages = session.query(InboxMessage).order_by(InboxMessage.id.desc()).limit(limit).all()
        data = []
        for m in messages:
            lead_name = m.lead.business_name if m.lead else "New Prospect"
            data.append({
                "id": m.id,
                "business_name": lead_name,
                "sender_email": m.sender_email,
                "recipient_account": m.recipient_account,
                "subject": m.subject,
                "body": m.body,
                "intent": m.classified_intent,
                "auto_responded": m.auto_responded,
                "auto_response_text": m.auto_response_text,
                "received_at": m.received_at.strftime("%Y-%m-%d %H:%M") if m.received_at else None
            })
        return data
    finally:
        session.close()

@app.get("/api/cities")
def api_get_cities():
    session = SessionLocal()
    try:
        cities = session.query(CityProgress).order_by(CityProgress.lon.desc()).all()
        return [{
            "id": c.id,
            "city": c.city,
            "state": c.state,
            "lon": c.lon,
            "scan_count": c.scan_count,
            "last_scanned_at": c.last_scanned_at.strftime("%Y-%m-%d %H:%M") if c.last_scanned_at else "Pending"
        } for c in cities]
    finally:
        session.close()

from sender import GmailAccountManager, test_gmail_credentials, process_email_queue, send_single_email, send_campaign_now

@app.get("/api/settings")
def api_get_settings():
    return {
        "gmail_user": settings.GMAIL_ACCOUNT_1_USER,
        "sender_name": settings.SENDER_NAME,
        "gemini_key": settings.GEMINI_API_KEY,
        "resend_key": settings.RESEND_API_KEY,
        "brevo_key": settings.BREVO_API_KEY,
        "dry_run": settings.DRY_RUN,
        "is_configured": bool((settings.GMAIL_ACCOUNT_1_USER and settings.GMAIL_ACCOUNT_1_PASS) or settings.RESEND_API_KEY or settings.BREVO_API_KEY)
    }

@app.post("/api/test-credentials")
def api_test_credentials(req: TestEmailRequest):
    success, message = test_gmail_credentials(req.gmail_user.strip(), req.gmail_pass.strip())
    return {"success": success, "message": message}

@app.post("/api/send-test-email")
def api_send_test_email(req: TestEmailRequest):
    user = req.gmail_user.strip() if req.gmail_user.strip() else settings.GMAIL_ACCOUNT_1_USER
    pwd = req.gmail_pass.strip() if req.gmail_pass.strip() else settings.GMAIL_ACCOUNT_1_PASS
    if not user or not pwd:
        return {"success": False, "message": "Please provide Gmail address and App Password."}
        
    subject = "✅ Client Hunter Agent: Test Email Delivery Confirmation"
    body_text = f"Hello {settings.SENDER_NAME},\n\nYour Client Hunter email outreach pipeline is active and working properly!\n\nSent from your verified Gmail account: {user}"
    
    success, err = send_single_email(
        sender_email=user,
        sender_password=pwd,
        recipient_email=user,
        subject=subject,
        body_text=body_text
    )
    if success:
        return {"success": True, "message": f"Real test email successfully delivered to {user}! Check your inbox."}
    else:
        return {"success": False, "message": f"Send failed: {err}"}

@app.post("/api/campaigns/{campaign_id}/send-now")
def api_send_campaign_now(campaign_id: int):
    success, message = send_campaign_now(campaign_id)
    return {"success": success, "message": message}

@app.post("/api/save-settings")
def api_save_settings(req: SettingsUpdateRequest):
    if req.gmail_user.strip():
        settings.GMAIL_ACCOUNT_1_USER = req.gmail_user.strip()
    if req.gmail_pass.strip():
        settings.GMAIL_ACCOUNT_1_PASS = req.gmail_pass.strip()
    if req.sender_name and req.sender_name.strip():
        settings.SENDER_NAME = req.sender_name.strip()
    if req.gemini_key is not None:
        settings.GEMINI_API_KEY = req.gemini_key.strip()
    if req.resend_key is not None:
        settings.RESEND_API_KEY = req.resend_key.strip()
    if req.brevo_key is not None:
        settings.BREVO_API_KEY = req.brevo_key.strip()
    if req.dry_run is not None:
        settings.DRY_RUN = req.dry_run
    return {"success": True, "message": "Settings saved and applied successfully!"}

@app.get("/api/scan-status")
def api_get_scan_status():
    from daemon import SCAN_PROGRESS
    return SCAN_PROGRESS

class OnDemandSearchRequest(BaseModel):
    query: Optional[str] = ""
    niche: Optional[str] = ""
    location: Optional[str] = ""

@app.post("/api/search/on-demand")
def api_search_on_demand(req: OnDemandSearchRequest, background_tasks: BackgroundTasks):
    from daemon import SCAN_PROGRESS, run_on_demand_pipeline
    if SCAN_PROGRESS.get("is_scanning", False):
        return {"success": False, "message": "A search or scan is already in progress. Please wait for it to complete."}
    
    if req.query and req.query.strip():
        search_query = req.query.strip()
        background_tasks.add_task(run_on_demand_pipeline, search_query, "")
        return {"success": True, "message": f"Live Google Maps deep search initiated for '{search_query}'."}
    else:
        niche = req.niche.strip() if req.niche and req.niche.strip() else "Dentist"
        location = req.location.strip() if req.location and req.location.strip() else "Miami, FL"
        background_tasks.add_task(run_on_demand_pipeline, niche, location)
        return {"success": True, "message": f"Live Google Maps & Web search initiated for '{niche}' in '{location}'."}

@app.post("/api/trigger/scan")
def api_trigger_scan(background_tasks: BackgroundTasks):
    from daemon import SCAN_PROGRESS
    if SCAN_PROGRESS.get("is_scanning", False):
        return {"success": False, "message": "A city scan is already in progress!"}
    background_tasks.add_task(job_discover_and_audit)
    return {"success": True, "message": "City scan and audit started."}

@app.post("/api/trigger/send")
def api_trigger_send(background_tasks: BackgroundTasks):
    background_tasks.add_task(process_email_queue, 5)
    return {"success": True, "message": "Email dispatcher started in background."}

@app.post("/api/trigger/inbox")
def api_trigger_inbox(background_tasks: BackgroundTasks):
    background_tasks.add_task(check_all_inboxes)
    return {"success": True, "message": "Inbox checker started in background."}

@app.post("/api/daemon/toggle")
def api_toggle_daemon():
    global DAEMON_RUNNING, DAEMON_THREAD
    if DAEMON_RUNNING:
        DAEMON_RUNNING = False
        return {"running": False, "message": "24/7 Autonomous agent stopped."}
    else:
        DAEMON_RUNNING = True
        DAEMON_THREAD = threading.Thread(target=daemon_worker_loop, daemon=True)
        DAEMON_THREAD.start()
        return {"running": True, "message": "24/7 Autonomous agent started!"}


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Client Hunter Agent Running</h1>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
