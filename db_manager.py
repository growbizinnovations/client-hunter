import os
import json
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import create_engine, func, and_, or_, text
from sqlalchemy.orm import sessionmaker, Session

from settings import settings
from models import (
    Base, CityProgress, Lead, WebsiteAudit, ContactInfo,
    EmailCampaign, InboxMessage, DailySendLog, AccountWarmup
)

# Ensure data directory exists
os.makedirs(os.path.dirname(settings.DATABASE_PATH) if os.path.dirname(settings.DATABASE_PATH) else ".", exist_ok=True)

ENGINE = create_engine(f"sqlite:///{settings.DATABASE_PATH}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)

DEFAULT_US_CITIES = [
    {"city": "Portland", "state": "ME", "lat": 43.6591, "lon": -70.2568, "tz": "America/New_York"},
    {"city": "Boston", "state": "MA", "lat": 42.3601, "lon": -71.0589, "tz": "America/New_York"},
    {"city": "Worcester", "state": "MA", "lat": 42.2626, "lon": -71.8023, "tz": "America/New_York"},
    {"city": "Providence", "state": "RI", "lat": 41.8240, "lon": -71.4128, "tz": "America/New_York"},
    {"city": "Hartford", "state": "CT", "lat": 41.7658, "lon": -72.6734, "tz": "America/New_York"},
    {"city": "New Haven", "state": "CT", "lat": 41.3083, "lon": -72.9279, "tz": "America/New_York"},
    {"city": "New York", "state": "NY", "lat": 40.7128, "lon": -74.0060, "tz": "America/New_York"},
    {"city": "Jersey City", "state": "NJ", "lat": 40.7178, "lon": -74.0431, "tz": "America/New_York"},
    {"city": "Newark", "state": "NJ", "lat": 40.7357, "lon": -74.1724, "tz": "America/New_York"},
    {"city": "Philadelphia", "state": "PA", "lat": 39.9526, "lon": -75.1652, "tz": "America/New_York"},
    {"city": "Allentown", "state": "PA", "lat": 40.6084, "lon": -75.4902, "tz": "America/New_York"},
    {"city": "Wilmington", "state": "DE", "lat": 39.7391, "lon": -75.5398, "tz": "America/New_York"},
    {"city": "Baltimore", "state": "MD", "lat": 39.2904, "lon": -76.6122, "tz": "America/New_York"},
    {"city": "Washington", "state": "DC", "lat": 38.9072, "lon": -77.0369, "tz": "America/New_York"},
    {"city": "Richmond", "state": "VA", "lat": 37.5407, "lon": -77.4360, "tz": "America/New_York"},
    {"city": "Virginia Beach", "state": "VA", "lat": 36.8529, "lon": -75.9780, "tz": "America/New_York"},
    {"city": "Raleigh", "state": "NC", "lat": 35.7796, "lon": -78.6382, "tz": "America/New_York"},
    {"city": "Charlotte", "state": "NC", "lat": 35.2271, "lon": -80.8431, "tz": "America/New_York"},
    {"city": "Charleston", "state": "SC", "lat": 32.7765, "lon": -79.9311, "tz": "America/New_York"},
    {"city": "Atlanta", "state": "GA", "lat": 33.7490, "lon": -84.3880, "tz": "America/New_York"},
    {"city": "Jacksonville", "state": "FL", "lat": 30.3322, "lon": -81.6557, "tz": "America/New_York"},
    {"city": "Orlando", "state": "FL", "lat": 28.5383, "lon": -81.3792, "tz": "America/New_York"},
    {"city": "Miami", "state": "FL", "lat": 25.7617, "lon": -80.1918, "tz": "America/New_York"},
    {"city": "Tampa", "state": "FL", "lat": 27.9506, "lon": -82.4572, "tz": "America/New_York"},
    {"city": "Pittsburgh", "state": "PA", "lat": 40.4406, "lon": -79.9959, "tz": "America/New_York"},
    {"city": "Cleveland", "state": "OH", "lat": 41.4993, "lon": -81.6944, "tz": "America/New_York"},
    {"city": "Columbus", "state": "OH", "lat": 39.9612, "lon": -82.9988, "tz": "America/New_York"},
    {"city": "Cincinnati", "state": "OH", "lat": 39.1031, "lon": -84.5120, "tz": "America/New_York"},
    {"city": "Detroit", "state": "MI", "lat": 42.3314, "lon": -83.0458, "tz": "America/New_York"},
    {"city": "Indianapolis", "state": "IN", "lat": 39.7684, "lon": -86.1581, "tz": "America/Indiana/Indianapolis"},
    {"city": "Louisville", "state": "KY", "lat": 38.2527, "lon": -85.7585, "tz": "America/New_York"},
    {"city": "Nashville", "state": "TN", "lat": 36.1627, "lon": -86.7816, "tz": "America/Chicago"},
    {"city": "Chicago", "state": "IL", "lat": 41.8781, "lon": -87.6298, "tz": "America/Chicago"},
    {"city": "Milwaukee", "state": "WI", "lat": 43.0389, "lon": -87.9065, "tz": "America/Chicago"},
    {"city": "St. Louis", "state": "MO", "lat": 38.6270, "lon": -90.1994, "tz": "America/Chicago"},
    {"city": "Minneapolis", "state": "MN", "lat": 44.9778, "lon": -93.2650, "tz": "America/Chicago"},
    {"city": "Kansas City", "state": "MO", "lat": 39.0997, "lon": -94.5786, "tz": "America/Chicago"},
    {"city": "Dallas", "state": "TX", "lat": 32.7767, "lon": -96.7970, "tz": "America/Chicago"},
    {"city": "Houston", "state": "TX", "lat": 29.7604, "lon": -95.3698, "tz": "America/Chicago"},
    {"city": "Austin", "state": "TX", "lat": 30.2672, "lon": -97.7431, "tz": "America/Chicago"},
    {"city": "San Antonio", "state": "TX", "lat": 29.4241, "lon": -98.4936, "tz": "America/Chicago"},
    {"city": "Denver", "state": "CO", "lat": 39.7392, "lon": -104.9903, "tz": "America/Denver"},
    {"city": "Phoenix", "state": "AZ", "lat": 33.4484, "lon": -112.0740, "tz": "America/Phoenix"},
    {"city": "Las Vegas", "state": "NV", "lat": 36.1699, "lon": -115.1398, "tz": "America/Los_Angeles"},
    {"city": "Salt Lake City", "state": "UT", "lat": 40.7608, "lon": -111.8910, "tz": "America/Denver"},
    {"city": "San Diego", "state": "CA", "lat": 32.7157, "lon": -117.1611, "tz": "America/Los_Angeles"},
    {"city": "Los Angeles", "state": "CA", "lat": 34.0522, "lon": -118.2437, "tz": "America/Los_Angeles"},
    {"city": "San Jose", "state": "CA", "lat": 37.3382, "lon": -121.8863, "tz": "America/Los_Angeles"},
    {"city": "San Francisco", "state": "CA", "lat": 37.7749, "lon": -122.4194, "tz": "America/Los_Angeles"},
    {"city": "Portland", "state": "OR", "lat": 45.5152, "lon": -122.6784, "tz": "America/Los_Angeles"},
    {"city": "Seattle", "state": "WA", "lat": 47.6062, "lon": -122.3321, "tz": "America/Los_Angeles"}
]

def init_db():
    """Initializes tables and seeds the East-to-West cities table if empty."""
    Base.metadata.create_all(bind=ENGINE)
    
    # Safe SQLite auto-migration for newly added columns
    with ENGINE.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE email_campaigns ADD COLUMN is_opened BOOLEAN DEFAULT 0"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE email_campaigns ADD COLUMN opened_at DATETIME"))
            conn.commit()
        except Exception:
            pass

    session = SessionLocal()
    try:
        city_count = session.query(CityProgress).count()
        if city_count == 0:
            cities_data = []
            candidate_paths = [
                os.path.join(os.path.dirname(__file__), "cities_east_to_west.json"),
                "cities_east_to_west.json",
                os.path.join("config", "cities_east_to_west.json")
            ]
            for p in candidate_paths:
                if os.path.exists(p):
                    try:
                        with open(p, "r", encoding="utf-8-sig") as f:
                            cities_data = json.load(f)
                            break
                    except Exception:
                        pass
                        
            if not cities_data:
                cities_data = DEFAULT_US_CITIES
                
            cities_data.sort(key=lambda x: x["lon"], reverse=True)
            
            for idx, c in enumerate(cities_data):
                city_obj = CityProgress(
                    city=c["city"],
                    state=c["state"],
                    lat=c.get("lat", 0.0),
                    lon=c.get("lon", 0.0),
                    timezone=c.get("tz", "America/New_York"),
                    cursor_index=idx
                )
                session.add(city_obj)
            session.commit()
    finally:
        session.close()

def get_account_warmup_status(account_email: str) -> Dict[str, Any]:
    """Calculates active day number and daily email cap based on warmup schedule."""
    if not account_email:
        return {"day": 1, "limit": 5, "sent_today": 0, "remaining": 5}
        
    session = SessionLocal()
    try:
        warmup = session.query(AccountWarmup).filter(AccountWarmup.account_email == account_email).first()
        today = date.today()
        
        if not warmup:
            warmup = AccountWarmup(account_email=account_email, first_active_date=today)
            session.add(warmup)
            session.commit()
            session.refresh(warmup)
            
        # Calculate active day count (Day 1 = 1, Day 2 = 2, etc.)
        day_diff = (today - warmup.first_active_date).days + 1
        
        # Ramp-up schedule requested:
        # Day 1: 5
        # Day 2: 10
        # Day 3: 15
        # Day 4+: 25 (max daily cap)
        if day_diff == 1:
            limit = 5
        elif day_diff == 2:
            limit = 10
        elif day_diff == 3:
            limit = 15
        else:
            limit = 25
            
        if warmup.custom_override_cap:
            limit = warmup.custom_override_cap
            
        today_str = today.isoformat()
        log = session.query(DailySendLog).filter(
            DailySendLog.account_email == account_email,
            DailySendLog.date_str == today_str
        ).first()
        sent_today = log.sent_count if log else 0
        
        return {
            "account": account_email,
            "warmup_day": day_diff,
            "daily_limit": limit,
            "sent_today": sent_today,
            "remaining": max(0, limit - sent_today),
            "first_active_date": warmup.first_active_date.isoformat()
        }
    finally:
        session.close()

def get_next_city_to_scan() -> Optional[CityProgress]:
    session = SessionLocal()
    try:
        count = session.query(CityProgress).count()
        if count == 0:
            init_db()
        unscanned = session.query(CityProgress).filter(CityProgress.last_scanned_at == None).order_by(CityProgress.lon.desc()).first()
        if unscanned:
            return unscanned
        oldest_scanned = session.query(CityProgress).order_by(CityProgress.last_scanned_at.asc(), CityProgress.lon.desc()).first()
        return oldest_scanned
    finally:
        session.close()

def mark_city_scanned(city_id: int):
    session = SessionLocal()
    try:
        city = session.query(CityProgress).filter(CityProgress.id == city_id).first()
        if city:
            city.last_scanned_at = datetime.utcnow()
            city.scan_count += 1
            session.commit()
    finally:
        session.close()

def get_or_create_lead(business_name: str, website_url: str, domain: str, city: str, state: str, niche: str, phone: str = None, address: str = None, rating: float = None) -> Tuple[Lead, bool]:
    session = SessionLocal()
    try:
        existing = session.query(Lead).filter(Lead.domain == domain).first()
        if existing:
            return existing, False
        
        new_lead = Lead(
            business_name=business_name,
            website_url=website_url,
            domain=domain,
            phone=phone,
            address=address,
            city=city,
            state=state,
            niche=niche,
            google_rating=rating,
            status="DISCOVERED"
        )
        session.add(new_lead)
        session.commit()
        session.refresh(new_lead)
        return new_lead, True
    finally:
        session.close()

def save_website_audit(lead_id: int, is_outdated: bool, score: int, copyright_year: Optional[int], is_responsive: bool, has_ssl: bool, has_viewport: bool, uses_tables: bool, uses_flash: bool, legacy_jquery: bool, load_time: float, html_size_kb: float, issues: List[str], positive_cues: List[str], summary: str):
    session = SessionLocal()
    try:
        audit = session.query(WebsiteAudit).filter(WebsiteAudit.lead_id == lead_id).first()
        if not audit:
            audit = WebsiteAudit(lead_id=lead_id)
            session.add(audit)
        
        audit.is_outdated = is_outdated
        audit.outdated_score = score
        audit.copyright_year = copyright_year
        audit.is_responsive = is_responsive
        audit.has_ssl = has_ssl
        audit.has_viewport = has_viewport
        audit.uses_tables_for_layout = uses_tables
        audit.uses_flash = uses_flash
        audit.legacy_jquery = legacy_jquery
        audit.load_time_sec = load_time
        audit.raw_html_size_kb = html_size_kb
        audit.issues_json = json.dumps(issues)
        audit.positive_cues_json = json.dumps(positive_cues)
        audit.summary = summary
        audit.audited_at = datetime.utcnow()
        
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.status = "AUDITED_OUTDATED" if is_outdated else "AUDITED_MODERN"
            lead.updated_at = datetime.utcnow()
            
        session.commit()
    finally:
        session.close()

def add_contact_email(lead_id: int, email: str, source_page: str = None) -> bool:
    session = SessionLocal()
    try:
        existing = session.query(ContactInfo).filter(ContactInfo.lead_id == lead_id, ContactInfo.email == email).first()
        if existing:
            return False
        
        contact = ContactInfo(
            lead_id=lead_id,
            email=email,
            source_page=source_page,
            is_verified=True
        )
        session.add(contact)
        
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if lead and lead.status in ["AUDITED_OUTDATED", "DISCOVERED"]:
            lead.status = "EMAIL_FOUND"
            lead.updated_at = datetime.utcnow()
            
        session.commit()
        return True
    finally:
        session.close()

def get_leads_ready_for_pitch(limit: int = 50) -> List[Lead]:
    session = SessionLocal()
    try:
        leads = session.query(Lead).join(ContactInfo).filter(
            Lead.status == "EMAIL_FOUND"
        ).order_by(Lead.id.asc()).limit(limit).all()
        result = []
        for l in leads:
            _ = l.audit
            _ = l.contacts
            result.append(l)
        return result
    finally:
        session.close()

def queue_email(lead_id: int, recipient_email: str, sender_account: str, subject: str, body_text: str, body_html: str, email_type: str = "INITIAL_OUTREACH") -> EmailCampaign:
    session = SessionLocal()
    try:
        campaign = EmailCampaign(
            lead_id=lead_id,
            recipient_email=recipient_email,
            sender_account=sender_account,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type=email_type,
            status="QUEUED"
        )
        session.add(campaign)
        
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.status = "EMAIL_QUEUED"
            lead.updated_at = datetime.utcnow()
            
        session.commit()
        session.refresh(campaign)
        return campaign
    finally:
        session.close()

def get_daily_sent_count(account_email: str) -> int:
    today_str = date.today().isoformat()
    session = SessionLocal()
    try:
        log = session.query(DailySendLog).filter(
            DailySendLog.account_email == account_email,
            DailySendLog.date_str == today_str
        ).first()
        return log.sent_count if log else 0
    finally:
        session.close()

def increment_daily_sent_count(account_email: str):
    today_str = date.today().isoformat()
    session = SessionLocal()
    try:
        log = session.query(DailySendLog).filter(
            DailySendLog.account_email == account_email,
            DailySendLog.date_str == today_str
        ).first()
        if not log:
            log = DailySendLog(account_email=account_email, date_str=today_str, sent_count=1)
            session.add(log)
        else:
            log.sent_count += 1
        session.commit()
    finally:
        session.close()

def mark_email_sent(campaign_id: int):
    session = SessionLocal()
    try:
        camp = session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
        if camp:
            camp.status = "SENT"
            camp.sent_at = datetime.utcnow()
            
            lead = session.query(Lead).filter(Lead.id == camp.lead_id).first()
            if lead:
                if camp.email_type == "INITIAL_OUTREACH":
                    lead.status = "EMAIL_SENT"
                elif camp.email_type == "FOLLOW_UP_1":
                    lead.status = "FOLLOW_UP_1"
                elif camp.email_type == "FOLLOW_UP_2":
                    lead.status = "FOLLOW_UP_2"
                lead.updated_at = datetime.utcnow()
                
            session.commit()
    finally:
        session.close()

def delete_lead(lead_id: int) -> bool:
    """Deletes a lead and its associated audits, contacts, campaigns, and messages."""
    session = SessionLocal()
    try:
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            session.delete(lead)
            session.commit()
            return True
        return False
    finally:
        session.close()

def cleanup_modern_leads() -> int:
    """Deletes all leads that have modern/good websites (not outdated)."""
    session = SessionLocal()
    try:
        modern_leads = session.query(Lead).filter(Lead.status == "AUDITED_MODERN").all()
        count = len(modern_leads)
        for l in modern_leads:
            session.delete(l)
        session.commit()
        return count
    finally:
        session.close()

def clear_all_leads_data() -> bool:
    """Clears all leads, audits, contacts, campaigns, and inbox messages for fresh start."""
    session = SessionLocal()
    try:
        session.query(InboxMessage).delete()
        session.query(EmailCampaign).delete()
        session.query(ContactInfo).delete()
        session.query(WebsiteAudit).delete()
        session.query(Lead).delete()
        session.commit()
        return True
    finally:
        session.close()

def set_active_target_city(city_name: str, state_name: str) -> bool:
    """Sets a specific city as the immediate active target city to scan."""
    session = SessionLocal()
    try:
        # Reset scan status on target city so it becomes the immediate next target
        target = session.query(CityProgress).filter(
            func.lower(CityProgress.city) == city_name.strip().lower(),
            func.lower(CityProgress.state) == state_name.strip().lower()
        ).first()
        if not target:
            target = CityProgress(city=city_name.strip(), state=state_name.strip(), lat=0.0, lon=999.0, cursor_index=0)
            session.add(target)
            session.commit()
            session.refresh(target)
            
        target.last_scanned_at = None
        target.scan_count = 0
        target.lon = 999.0 # Highest priority
        session.commit()
        return True
    finally:
        session.close()

def get_stats() -> Dict[str, Any]:
    session = SessionLocal()
    try:
        total_cities = session.query(CityProgress).count()
        scanned_cities = session.query(CityProgress).filter(CityProgress.scan_count > 0).count()
        total_leads = session.query(Lead).count()
        outdated_leads = session.query(Lead).filter(Lead.status.in_(["AUDITED_OUTDATED", "EMAIL_FOUND", "EMAIL_QUEUED", "EMAIL_SENT", "FOLLOW_UP_1", "FOLLOW_UP_2", "REPLIED", "MEETING_BOOKED"])).count()
        modern_leads = session.query(Lead).filter(Lead.status == "AUDITED_MODERN").count()
        emails_found = session.query(ContactInfo).count()
        emails_sent = session.query(EmailCampaign).filter(EmailCampaign.status == "SENT").count()
        replies_received = session.query(InboxMessage).count()
        requirements_received = session.query(InboxMessage).filter(InboxMessage.classified_intent == "INTERESTED").count()
        
        today_str = date.today().isoformat()
        today_sent = session.query(func.sum(DailySendLog.sent_count)).filter(DailySendLog.date_str == today_str).scalar() or 0
        
        primary_account = settings.GMAIL_ACCOUNT_1_USER or "sender1@gmail.com"
        warmup_info = get_account_warmup_status(primary_account)
        
        return {
            "total_cities": total_cities,
            "scanned_cities": scanned_cities,
            "total_leads": total_leads,
            "outdated_leads": outdated_leads,
            "modern_leads": modern_leads,
            "emails_found": emails_found,
            "emails_sent": emails_sent,
            "replies_received": replies_received,
            "requirements_received": requirements_received,
            "today_sent": today_sent,
            "warmup_day": warmup_info["warmup_day"],
            "today_limit": warmup_info["daily_limit"],
            "primary_account": primary_account
        }
    finally:
        session.close()
