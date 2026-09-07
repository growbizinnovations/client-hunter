# 🤖 24/7 Autonomous Client Hunter & Cold Outreach Agent

An end-to-end autonomous agent that systematically traverses US cities from East to West, audits local small business websites, detects outdated designs and technical flaws, extracts verified contact emails, generates tailored AI redesign pitches ($500 offer), and sends 60 emails/day distributed across 4 Gmail accounts (15/day each) with automated follow-ups and inbox reply scheduling.

---

## 🚀 Key Features

1. **East-to-West US City Progression**: Traverses 80+ major US metropolitan areas and towns ordered strictly by longitude starting from the East Coast (Maine, Massachusetts, New York, Pennsylvania, Florida, Georgia, etc. moving West toward California).
2. **Technical Website Auditor**: Automatically detects:
   - Missing mobile viewport / non-responsive fixed layouts
   - Insecure HTTP / missing SSL certificates
   - Outdated copyright dates (e.g. `© 2014-2019`)
   - Legacy tech stacks (obsolete jQuery 1.x, Flash, table-based layouts)
   - Slow initial page load times and missing social metadata
3. **Contact Email Extractor**: Crawls homepages, `/contact`, `/about`, and footers to extract clean, verified business emails.
4. **AI Pitch Generator (Gemini + Dynamic Engine)**: Formulates concise, personalized emails referencing the specific audit flaws found and proposing a risk-free free preview with a flat **$500 redesign price**.
5. **4-Account Gmail Dispatcher**: Distributes sends evenly (15 emails/account = 60/day) with natural randomized delays (2–6 mins) to protect inbox reputation.
6. **24/7 Inbox Monitoring & Auto-Responder**: Listens for responses on all 4 Gmail accounts, uses AI to classify intent (`INTERESTED`, `QUESTION`, `NOT_INTERESTED`, `UNSUBSCRIBE`), and automatically responds with requirements questionnaires or meeting booking links.
7. **Automated Follow-Up Sequences**: Automatically queues gentle follow-ups at 3 days and 7 days for non-responders.
8. **Interactive Web Dashboard & CLI**: Monitor conversion funnels, inspect audit details, review queued emails, and trigger manual batches.

---

## 🛠️ Quick Start & Setup

### 1. Configuration (`.env`)
Copy `.env.example` to `.env` and fill in your details:
```bash
cp .env.example .env
```

Set up your 4 Gmail accounts:
- Ensure 2-Factor Authentication (2FA) is turned ON for each Gmail account.
- Generate an **App Password** for each account at: [Google Account Security -> App Passwords](https://myaccount.google.com/apppasswords).
- Paste the 16-character App Passwords into `.env`.

Optional:
- Set `GEMINI_API_KEY` for Google Gemini AI copywriting and reply intent analysis.
- Set `SCHEDULING_LINK` (e.g. your Calendly or Cal.com URL).
- Set `DRY_RUN=False` when you are ready to send live emails (`DRY_RUN=True` simulates and logs everything safely).

---

## 💻 CLI Commands

Run commands using the virtual environment:

```powershell
# 1. View Pipeline Metrics & Account Capacity
.\.venv\Scripts\python.exe main.py stats

# 2. Run a Discovery & Audit scan for the next East-to-West city
.\.venv\Scripts\python.exe main.py scan-now

# 3. Dispatch a batch of queued emails
.\.venv\Scripts\python.exe main.py send-batch

# 4. Check all 4 Gmail inboxes for replies & run auto-responder
.\.venv\Scripts\python.exe main.py check-inbox

# 5. Start the 24/7 Continuous Background Daemon
.\.venv\Scripts\python.exe main.py run-daemon

# 6. Launch the Visual Web Dashboard
.\.venv\Scripts\python.exe main.py dashboard
```

---

## 📁 Project Architecture

```
client-hunter-agent/
├── config/
│   ├── settings.py              # Configuration settings & env variables
│   └── cities_east_to_west.json # US cities ranked East-to-West by longitude
├── database/
│   ├── models.py                # SQLAlchemy models (Leads, Audits, Campaigns, Inboxes)
│   └── db_manager.py            # SQLite database manager & stats
├── modules/
│   ├── discovery.py             # Business finder across target niches
│   ├── website_auditor.py       # Outdated website detection & scoring engine
│   ├── email_extractor.py       # Contact page crawler & email harvester
│   ├── ai_pitcher.py            # Gemini AI & template email generator ($500 offer)
│   ├── sender.py                # 4-Account Gmail dispatcher & rate limiter
│   ├── inbox_monitor.py         # IMAP reply monitor & intent classifier
│   └── follow_up.py             # 3-day and 7-day follow-up automations
├── dashboard/
│   └── app.py                   # Streamlit interactive web dashboard
├── daemon.py                    # 24/7 APScheduler continuous background worker
├── main.py                      # Multi-command CLI runner
└── requirements.txt             # Project dependencies
```
