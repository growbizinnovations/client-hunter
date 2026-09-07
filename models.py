from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, Text, DateTime, Date, ForeignKey, Index, create_engine
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class CityProgress(Base):
    __tablename__ = "city_progress"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String(100), nullable=False)
    state = Column(String(10), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    timezone = Column(String(50), default="America/New_York")
    last_scanned_at = Column(DateTime, nullable=True)
    scan_count = Column(Integer, default=0)
    cursor_index = Column(Integer, default=0)
    
    __table_args__ = (
        Index("idx_city_state", "city", "state", unique=True),
        Index("idx_lon", "lon"),
    )

class Lead(Base):
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    business_name = Column(String(255), nullable=False)
    website_url = Column(String(500), nullable=False)
    domain = Column(String(255), nullable=False, unique=True)
    phone = Column(String(50), nullable=True)
    address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(10), nullable=False)
    niche = Column(String(100), nullable=False)
    google_rating = Column(Float, nullable=True)
    
    # Status: DISCOVERED, AUDITED_OUTDATED, AUDITED_MODERN, EMAIL_FOUND, NO_EMAIL_FOUND, EMAIL_QUEUED, EMAIL_SENT, FOLLOW_UP_1, FOLLOW_UP_2, REPLIED, MEETING_BOOKED, UNSUBSCRIBED
    status = Column(String(50), default="DISCOVERED")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    audit = relationship("WebsiteAudit", back_populates="lead", uselist=False, cascade="all, delete-orphan")
    contacts = relationship("ContactInfo", back_populates="lead", cascade="all, delete-orphan")
    emails = relationship("EmailCampaign", back_populates="lead", cascade="all, delete-orphan")
    inbox_messages = relationship("InboxMessage", back_populates="lead", cascade="all, delete-orphan")

class WebsiteAudit(Base):
    __tablename__ = "website_audits"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), unique=True, nullable=False)
    is_outdated = Column(Boolean, default=False)
    outdated_score = Column(Integer, default=0)
    copyright_year = Column(Integer, nullable=True)
    is_responsive = Column(Boolean, default=True)
    has_ssl = Column(Boolean, default=True)
    has_viewport = Column(Boolean, default=True)
    uses_tables_for_layout = Column(Boolean, default=False)
    uses_flash = Column(Boolean, default=False)
    legacy_jquery = Column(Boolean, default=False)
    load_time_sec = Column(Float, default=0.0)
    raw_html_size_kb = Column(Float, default=0.0)
    issues_json = Column(Text, default="[]")
    positive_cues_json = Column(Text, default="[]")
    summary = Column(Text, nullable=True)
    audited_at = Column(DateTime, default=datetime.utcnow)
    
    lead = relationship("Lead", back_populates="audit")

class ContactInfo(Base):
    __tablename__ = "contacts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    email = Column(String(255), nullable=False)
    source_page = Column(String(500), nullable=True)
    is_verified = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    lead = relationship("Lead", back_populates="contacts")
    
    __table_args__ = (
        Index("idx_lead_email", "lead_id", "email", unique=True),
    )

class EmailCampaign(Base):
    __tablename__ = "email_campaigns"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    recipient_email = Column(String(255), nullable=False)
    sender_account = Column(String(255), nullable=False)
    subject = Column(String(300), nullable=False)
    body_text = Column(Text, nullable=False)
    body_html = Column(Text, nullable=True)
    email_type = Column(String(50), default="INITIAL_OUTREACH")
    status = Column(String(50), default="QUEUED") # QUEUED, SENT, FAILED
    is_opened = Column(Boolean, default=False)
    opened_at = Column(DateTime, nullable=True)
    scheduled_for = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    lead = relationship("Lead", back_populates="emails")

class InboxMessage(Base):
    __tablename__ = "inbox_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    sender_email = Column(String(255), nullable=False)
    recipient_account = Column(String(255), nullable=False)
    subject = Column(String(300), nullable=False)
    body = Column(Text, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow)
    classified_intent = Column(String(50), default="UNKNOWN")
    auto_responded = Column(Boolean, default=False)
    auto_response_text = Column(Text, nullable=True)
    
    lead = relationship("Lead", back_populates="inbox_messages")

class DailySendLog(Base):
    __tablename__ = "daily_send_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_email = Column(String(255), nullable=False)
    date_str = Column(String(20), nullable=False) # YYYY-MM-DD
    sent_count = Column(Integer, default=0)
    
    __table_args__ = (
        Index("idx_account_date", "account_email", "date_str", unique=True),
    )

class AccountWarmup(Base):
    __tablename__ = "account_warmup"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_email = Column(String(255), nullable=False, unique=True)
    first_active_date = Column(Date, default=date.today)
    custom_override_cap = Column(Integer, nullable=True)
