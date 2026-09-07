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

@app.post("/api/trigger/scan")
def api_trigger_scan(background_tasks: BackgroundTasks):
    background_tasks.add_task(job_discover_and_audit)
    return {"success": True, "message": "City scan and audit started in background."}

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

EMBEDDED_HTML = "<!DOCTYPE html>\n<html lang=\"en\" class=\"dark\">\n<head>\n  <meta charset=\"UTF-8\" />\n  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n  <title>Client Hunter 24/7 - Autonomous Website Outreach</title>\n  <script src=\"https://cdn.tailwindcss.com\"></script>\n  <script src=\"https://unpkg.com/lucide@latest\"></script>\n  <script>\n    tailwind.config = {\n      darkMode: 'class',\n      theme: {\n        extend: {\n          colors: {\n            brand: { 50: '#eef2ff', 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca' },\n            darkbg: '#0f172a', darkcard: '#1e293b', darkborder: '#334155'\n          }\n        }\n      }\n    }\n  </script>\n  <link rel=\"stylesheet\" href=\"/static/style.css\" />\n</head>\n<body class=\"bg-darkbg text-slate-100 min-h-screen flex flex-col\">\n  <header class=\"border-b border-darkborder bg-darkcard/80 backdrop-blur sticky top-0 z-50\">\n    <div class=\"max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between\">\n      <div class=\"flex items-center space-x-3\">\n        <div class=\"h-10 w-10 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-400 flex items-center justify-center shadow-lg shadow-brand-500/30\">\n          <i data-lucide=\"bot\" class=\"w-6 h-6 text-white\"></i>\n        </div>\n        <div>\n          <h1 class=\"font-bold text-lg leading-tight flex items-center gap-2\">\n            Client Hunter <span class=\"text-xs px-2 py-0.5 rounded-full bg-brand-500/20 text-brand-400 border border-brand-500/30\">24/7 Agent</span>\n          </h1>\n          <p class=\"text-xs text-slate-400\">East-to-West US Outreach \u2022 $500 Website Redesign Demo</p>\n        </div>\n      </div>\n      <div class=\"flex items-center space-x-4\">\n        <div id=\"mode-badge\" class=\"px-3 py-1 text-xs font-semibold rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 flex items-center gap-1.5\">\n          <span class=\"w-2 h-2 rounded-full bg-yellow-400 animate-pulse\"></span> DRY RUN (Simulated)\n        </div>\n        <button id=\"toggle-daemon-btn\" onclick=\"toggleDaemon()\" class=\"px-4 py-2 text-sm font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-2 shadow-md transition\">\n          <i data-lucide=\"play\" class=\"w-4 h-4\"></i> <span>Start 24/7 Autonomous Worker</span>\n        </button>\n      </div>\n    </div>\n  </header>\n\n  <main class=\"max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full\">\n    <div class=\"grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8\">\n      <div class=\"bg-darkcard border border-darkborder rounded-xl p-4 shadow-sm\">\n        <div class=\"text-xs font-medium text-slate-400 flex items-center justify-between\">\n          <span>Cities Route</span><i data-lucide=\"map-pin\" class=\"w-4 h-4 text-indigo-400\"></i>\n        </div>\n        <div class=\"text-2xl font-bold mt-2 text-white\" id=\"stat-cities\">-</div>\n        <div class=\"text-xs text-slate-500 mt-1\">East to West cursor</div>\n      </div>\n      <div class=\"bg-darkcard border border-darkborder rounded-xl p-4 shadow-sm\">\n        <div class=\"text-xs font-medium text-slate-400 flex items-center justify-between\">\n          <span>Businesses Found</span><i data-lucide=\"building\" class=\"w-4 h-4 text-blue-400\"></i>\n        </div>\n        <div class=\"text-2xl font-bold mt-2 text-white\" id=\"stat-leads\">-</div>\n        <div class=\"text-xs text-slate-500 mt-1\">Discovered leads</div>\n      </div>\n      <div class=\"bg-darkcard border border-darkborder rounded-xl p-4 shadow-sm\">\n        <div class=\"text-xs font-medium text-slate-400 flex items-center justify-between\">\n          <span>Outdated Websites</span><i data-lucide=\"alert-triangle\" class=\"w-4 h-4 text-rose-400\"></i>\n        </div>\n        <div class=\"text-2xl font-bold mt-2 text-rose-400\" id=\"stat-outdated\">-</div>\n        <div class=\"text-xs text-slate-500 mt-1\">Qualified targets</div>\n      </div>\n      <div class=\"bg-darkcard border border-darkborder rounded-xl p-4 shadow-sm\">\n        <div class=\"text-xs font-medium text-slate-400 flex items-center justify-between\">\n          <span>Emails Harvested</span><i data-lucide=\"mail-search\" class=\"w-4 h-4 text-emerald-400\"></i>\n        </div>\n        <div class=\"text-2xl font-bold mt-2 text-white\" id=\"stat-emails\">-</div>\n        <div class=\"text-xs text-slate-500 mt-1\">Verified contacts</div>\n      </div>\n      <div class=\"bg-darkcard border border-darkborder rounded-xl p-4 shadow-sm\">\n        <div class=\"text-xs font-medium text-slate-400 flex items-center justify-between\">\n          <span>Sent Today</span><i data-lucide=\"send\" class=\"w-4 h-4 text-yellow-400\"></i>\n        </div>\n        <div class=\"text-2xl font-bold mt-2 text-yellow-400\" id=\"stat-sent-today\">-</div>\n        <div class=\"text-xs text-slate-400 mt-1\" id=\"stat-warmup-info\">Warmup Cap: -</div>\n      </div>\n      <div class=\"bg-darkcard border border-darkborder rounded-xl p-4 shadow-sm\">\n        <div class=\"text-xs font-medium text-slate-400 flex items-center justify-between\">\n          <span>Prospect Replies</span><i data-lucide=\"message-square\" class=\"w-4 h-4 text-purple-400\"></i>\n        </div>\n        <div class=\"text-2xl font-bold mt-2 text-purple-400\" id=\"stat-replies\">-</div>\n        <div class=\"text-xs text-slate-500 mt-1\">Requirements received</div>\n      </div>\n    </div>\n\n    <div class=\"bg-darkcard border border-darkborder rounded-xl p-4 mb-8 flex flex-wrap items-center justify-between gap-4\">\n      <div class=\"flex items-center space-x-2\">\n        <span class=\"text-sm font-semibold text-slate-300\">Quick Manual Actions:</span>\n      </div>\n      <div class=\"flex flex-wrap items-center gap-3\">\n        <button onclick=\"triggerScan()\" class=\"px-4 py-2 text-sm font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-darkborder flex items-center gap-2 transition\">\n          <i data-lucide=\"search\" class=\"w-4 h-4 text-indigo-400\"></i> Scan Next City\n        </button>\n        <button onclick=\"triggerSend()\" class=\"px-4 py-2 text-sm font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-darkborder flex items-center gap-2 transition\">\n          <i data-lucide=\"send\" class=\"w-4 h-4 text-yellow-400\"></i> Send Queued Batch\n        </button>\n        <button onclick=\"triggerInbox()\" class=\"px-4 py-2 text-sm font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-darkborder flex items-center gap-2 transition\">\n          <i data-lucide=\"inbox\" class=\"w-4 h-4 text-purple-400\"></i> Check Inbox Replies\n        </button>\n      </div>\n    </div>\n\n    <div class=\"border-b border-darkborder flex space-x-6 text-sm font-medium mb-6\">\n      <button onclick=\"switchTab('leads')\" id=\"tab-btn-leads\" class=\"pb-3 border-b-2 border-brand-500 text-brand-400 flex items-center gap-2 font-semibold\">\n        <i data-lucide=\"target\" class=\"w-4 h-4\"></i> Discovered Leads & Audits\n      </button>\n      <button onclick=\"switchTab('campaigns')\" id=\"tab-btn-campaigns\" class=\"pb-3 border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2\">\n        <i data-lucide=\"mail\" class=\"w-4 h-4\"></i> Email Outreach Queue\n      </button>\n      <button onclick=\"switchTab('inbox')\" id=\"tab-btn-inbox\" class=\"pb-3 border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2\">\n        <i data-lucide=\"message-circle\" class=\"w-4 h-4\"></i> Inbound Requirements (<span id=\"inbox-count\">0</span>)\n      </button>\n      <button onclick=\"switchTab('cities')\" id=\"tab-btn-cities\" class=\"pb-3 border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2\">\n        <i data-lucide=\"map\" class=\"w-4 h-4\"></i> East-to-West Route\n      </button>\n      <button onclick=\"switchTab('settings')\" id=\"tab-btn-settings\" class=\"pb-3 border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2\">\n        <i data-lucide=\"settings\" class=\"w-4 h-4\"></i> Gmail & Warmup Settings\n      </button>\n    </div>\n\n    <div id=\"tab-leads\" class=\"tab-content\">\n      <div class=\"bg-darkcard border border-darkborder rounded-xl overflow-hidden shadow\">\n        <div class=\"p-4 border-b border-darkborder flex items-center justify-between\">\n          <h2 class=\"font-semibold text-white flex items-center gap-2\">\n            <i data-lucide=\"list\" class=\"w-4 h-4 text-brand-400\"></i> Discovered Businesses & Website Health\n          </h2>\n          <span class=\"text-xs text-slate-400\" id=\"leads-count-label\">Loading leads...</span>\n        </div>\n        <div class=\"overflow-x-auto\">\n          <table class=\"w-full text-left text-sm text-slate-300\">\n            <thead class=\"bg-slate-900/60 text-xs uppercase font-semibold text-slate-400 border-b border-darkborder\">\n              <tr>\n                <th class=\"px-4 py-3\">Business / Domain</th>\n                <th class=\"px-4 py-3\">Location & Niche</th>\n                <th class=\"px-4 py-3\">Website Health</th>\n                <th class=\"px-4 py-3\">Detected Issues</th>\n                <th class=\"px-4 py-3\">Contact Email</th>\n                <th class=\"px-4 py-3\">Status</th>\n              </tr>\n            </thead>\n            <tbody id=\"leads-table-body\" class=\"divide-y divide-darkborder\">\n              <tr><td colspan=\"6\" class=\"p-6 text-center text-slate-500\">Loading leads data...</td></tr>\n            </tbody>\n          </table>\n        </div>\n      </div>\n    </div>\n\n    <div id=\"tab-campaigns\" class=\"tab-content hidden\">\n      <div class=\"bg-darkcard border border-darkborder rounded-xl p-6 shadow\">\n        <div class=\"flex items-center justify-between mb-4\">\n          <h2 class=\"font-semibold text-white flex items-center gap-2\">\n            <i data-lucide=\"send\" class=\"w-4 h-4 text-yellow-400\"></i> Personalized Email Outreach Queue ($500 Demo Offer)\n          </h2>\n        </div>\n        <div id=\"campaigns-list\" class=\"space-y-4\">\n          <div class=\"text-center py-8 text-slate-500\">Loading campaign queue...</div>\n        </div>\n      </div>\n    </div>\n\n    <div id=\"tab-inbox\" class=\"tab-content hidden\">\n      <div class=\"bg-darkcard border border-darkborder rounded-xl p-6 shadow\">\n        <div class=\"flex items-center justify-between mb-4\">\n          <h2 class=\"font-semibold text-white flex items-center gap-2\">\n            <i data-lucide=\"inbox\" class=\"w-4 h-4 text-purple-400\"></i> Incoming Replies & Website Requirements\n          </h2>\n        </div>\n        <div id=\"inbox-list\" class=\"space-y-4\">\n          <div class=\"text-center py-8 text-slate-500\">No prospect replies yet.</div>\n        </div>\n      </div>\n    </div>\n\n    <div id=\"tab-cities\" class=\"tab-content hidden\">\n      <div class=\"bg-darkcard border border-darkborder rounded-xl p-6 shadow\">\n        <h2 class=\"font-semibold text-white mb-4 flex items-center gap-2\">\n          <i data-lucide=\"compass\" class=\"w-4 h-4 text-indigo-400\"></i> 136 US Cities Traversal Route (East to West by Longitude)\n        </h2>\n        <div class=\"overflow-x-auto max-h-[600px]\">\n          <table class=\"w-full text-left text-sm text-slate-300\">\n            <thead class=\"bg-slate-900/60 text-xs uppercase font-semibold text-slate-400 border-b border-darkborder sticky top-0\">\n              <tr>\n                <th class=\"px-4 py-3\">#</th>\n                <th class=\"px-4 py-3\">City, State</th>\n                <th class=\"px-4 py-3\">Longitude (East \u2794 West)</th>\n                <th class=\"px-4 py-3\">Times Scanned</th>\n                <th class=\"px-4 py-3\">Last Scanned Date</th>\n              </tr>\n            </thead>\n            <tbody id=\"cities-table-body\" class=\"divide-y divide-darkborder\">\n              <tr><td colspan=\"5\" class=\"p-6 text-center text-slate-500\">Loading cities...</td></tr>\n            </tbody>\n          </table>\n        </div>\n      </div>\n    </div>\n\n    <div id=\"tab-settings\" class=\"tab-content hidden\">\n      <div class=\"grid grid-cols-1 md:grid-cols-2 gap-6\">\n        <div class=\"bg-darkcard border border-darkborder rounded-xl p-6 shadow\">\n          <h2 class=\"font-semibold text-white mb-2 flex items-center gap-2\">\n            <i data-lucide=\"mail\" class=\"w-4 h-4 text-red-400\"></i> Gmail Account Login Credentials\n          </h2>\n          <p class=\"text-xs text-slate-400 mb-6\">Enter your Gmail address and 16-character App Password to start sending.</p>\n          \n          <div class=\"space-y-4\">\n            <div>\n              <label class=\"block text-xs font-semibold text-slate-300 mb-1\">Gmail Address</label>\n              <input type=\"email\" id=\"input-gmail-user\" placeholder=\"yourname@gmail.com\" class=\"w-full bg-slate-900 border border-darkborder rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500\" />\n            </div>\n            <div>\n              <label class=\"block text-xs font-semibold text-slate-300 mb-1\">Gmail App Password (16 characters)</label>\n              <input type=\"password\" id=\"input-gmail-pass\" placeholder=\"xxxx xxxx xxxx xxxx\" class=\"w-full bg-slate-900 border border-darkborder rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500\" />\n              <p class=\"text-[11px] text-slate-500 mt-1\">Generate via Google Account -> Security -> 2-Step Verification -> App Passwords</p>\n            </div>\n            <div>\n              <label class=\"block text-xs font-semibold text-slate-300 mb-1\">Sender Display Name</label>\n              <input type=\"text\" id=\"input-sender-name\" value=\"Tushar\" class=\"w-full bg-slate-900 border border-darkborder rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500\" />\n            </div>\n            <div>\n              <label class=\"block text-xs font-semibold text-slate-300 mb-1\">Gemini API Key (Optional)</label>\n              <input type=\"password\" id=\"input-gemini-key\" placeholder=\"AIzaSy...\" class=\"w-full bg-slate-900 border border-darkborder rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500\" />\n            </div>\n            <div class=\"pt-2 flex items-center justify-between\">\n              <label class=\"flex items-center gap-2 text-xs font-medium text-slate-300 cursor-pointer\">\n                <input type=\"checkbox\" id=\"input-dry-run\" class=\"rounded bg-slate-900 border-darkborder text-brand-600 focus:ring-0\" />\n                <span>Dry Run Mode (Simulate without sending real emails)</span>\n              </label>\n            </div>\n            <div class=\"pt-4 flex gap-3\">\n              <button onclick=\"testCredentials()\" class=\"flex-1 px-4 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-darkborder text-sm font-semibold transition\">\n                Test Connection\n              </button>\n              <button onclick=\"saveSettings()\" class=\"flex-1 px-4 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-semibold transition shadow-md\">\n                Save & Apply Settings\n              </button>\n            </div>\n            <div id=\"settings-status-msg\" class=\"text-xs hidden p-3 rounded-lg mt-2\"></div>\n          </div>\n        </div>\n\n        <div class=\"bg-darkcard border border-darkborder rounded-xl p-6 shadow flex flex-col justify-between\">\n          <div>\n            <h2 class=\"font-semibold text-white mb-2 flex items-center gap-2\">\n              <i data-lucide=\"flame\" class=\"w-4 h-4 text-orange-400\"></i> Automated Warmup & Ramp-Up Protection\n            </h2>\n            <p class=\"text-xs text-slate-400 mb-6\">Protects your Gmail sender reputation from spam filters by scaling volume safely.</p>\n\n            <div class=\"space-y-3 text-sm\">\n              <div class=\"flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-darkborder\">\n                <div class=\"flex items-center gap-2\">\n                  <span class=\"w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-400 text-xs font-bold flex items-center justify-center\">1</span>\n                  <span class=\"font-medium text-white\">Day 1</span>\n                </div>\n                <span class=\"font-bold text-slate-300\">5 emails / day</span>\n              </div>\n              <div class=\"flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-darkborder\">\n                <div class=\"flex items-center gap-2\">\n                  <span class=\"w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-400 text-xs font-bold flex items-center justify-center\">2</span>\n                  <span class=\"font-medium text-white\">Day 2</span>\n                </div>\n                <span class=\"font-bold text-slate-300\">10 emails / day</span>\n              </div>\n              <div class=\"flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-darkborder\">\n                <div class=\"flex items-center gap-2\">\n                  <span class=\"w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-400 text-xs font-bold flex items-center justify-center\">3</span>\n                  <span class=\"font-medium text-white\">Day 3</span>\n                </div>\n                <span class=\"font-bold text-slate-300\">15 emails / day</span>\n              </div>\n              <div class=\"flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-emerald-500/30 bg-emerald-500/5\">\n                <div class=\"flex items-center gap-2\">\n                  <span class=\"w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-bold flex items-center justify-center\">4+</span>\n                  <span class=\"font-medium text-emerald-300\">Day 4 & Ongoing</span>\n                </div>\n                <span class=\"font-bold text-emerald-400\">25 emails / day</span>\n              </div>\n            </div>\n          </div>\n          <div class=\"mt-6 p-4 rounded-xl bg-slate-900 border border-darkborder\">\n            <div class=\"text-xs text-slate-400\">Current Warmup Stage:</div>\n            <div class=\"text-lg font-bold text-white mt-1\" id=\"warmup-summary-text\">Day 1 Active (5 emails max today)</div>\n          </div>\n        </div>\n      </div>\n    </div>\n  </main>\n\n  <footer class=\"border-t border-darkborder py-4 text-center text-xs text-slate-500\">\n    Client Hunter 24/7 Autonomous Agent \u2022 Running locally on your machine\n  </footer>\n\n  <script src=\"/static/app.js\"></script>\n</body>\n</html>"

@app.get("/")
def serve_index():
    return HTMLResponse(content=EMBEDDED_HTML, status_code=200)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
