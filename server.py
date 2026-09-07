import os
import json
import sys
import json
import threading
import time
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

from settings import settings
from db_manager import init_db, get_stats, get_account_warmup_status, SessionLocal
from models import CityProgress, Lead, WebsiteAudit, ContactInfo, EmailCampaign, InboxMessage, DailySendLog
from sender import GmailAccountManager, test_gmail_credentials, process_email_queue
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

@app.get("/api/leads")
def api_get_leads(limit: int = 100):
    session = SessionLocal()
    try:
        leads = session.query(Lead).order_by(Lead.id.desc()).limit(limit).all()
        data = []
        for l in leads:
            issues = []
            if l.audit and l.audit.issues_json:
                try:
                    issues = json.loads(l.audit.issues_json)
                except Exception:
                    issues = []
            data.append({
                "id": l.id,
                "business_name": l.business_name,
                "domain": l.domain,
                "website_url": l.website_url,
                "city": l.city,
                "state": l.state,
                "niche": l.niche,
                "status": l.status,
                "outdated_score": l.audit.outdated_score if l.audit else None,
                "copyright_year": l.audit.copyright_year if l.audit else None,
                "issues": issues,
                "emails": [c.email for c in l.contacts],
                "created_at": l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else None
            })
        return data
    finally:
        session.close()

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
                "email_type": c.email_type,
                "sent_at": c.sent_at.strftime("%Y-%m-%d %H:%M") if c.sent_at else None,
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

@app.post("/api/test-credentials")
def api_test_credentials(req: TestEmailRequest):
    success, message = test_gmail_credentials(req.gmail_user.strip(), req.gmail_pass.strip())
    return {"success": success, "message": message}

@app.post("/api/save-settings")
def api_save_settings(req: SettingsUpdateRequest):
    settings.GMAIL_ACCOUNT_1_USER = req.gmail_user.strip()
    settings.GMAIL_ACCOUNT_1_PASS = req.gmail_pass.strip()
    settings.SENDER_NAME = req.sender_name.strip() if req.sender_name else settings.SENDER_NAME
    settings.DRY_RUN = req.dry_run if req.dry_run is not None else settings.DRY_RUN
    return {"success": True, "message": "Settings saved successfully!"}

@app.get("/api/scan-status")
def api_get_scan_status():
    from daemon import SCAN_PROGRESS
    return SCAN_PROGRESS

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
