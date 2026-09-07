from datetime import datetime, timedelta
from typing import List

from settings import settings
from db_manager import SessionLocal, queue_email
from models import Lead, EmailCampaign, ContactInfo
from ai_pitcher import generate_followup_email

def check_and_queue_follow_ups() -> int:
    """Finds non-responsive leads eligible for Follow-Up #1 or Follow-Up #2 and queues them."""
    session = SessionLocal()
    queued_count = 0
    now = datetime.utcnow()
    
    try:
        # 1. Follow-Up #1 (3 days after initial email)
        fu1_threshold = now - timedelta(days=settings.FIRST_FOLLOW_UP_DAYS)
        eligible_for_fu1 = session.query(Lead).filter(
            Lead.status == "EMAIL_SENT"
        ).all()
        
        for lead in eligible_for_fu1:
            # Check when the last email was sent
            last_email = session.query(EmailCampaign).filter(
                EmailCampaign.lead_id == lead.id,
                EmailCampaign.email_type == "INITIAL_OUTREACH",
                EmailCampaign.status == "SENT"
            ).order_by(EmailCampaign.sent_at.desc()).first()
            
            if last_email and last_email.sent_at and last_email.sent_at <= fu1_threshold:
                contact = session.query(ContactInfo).filter(ContactInfo.lead_id == lead.id).first()
                if contact:
                    fu_content = generate_followup_email(lead.business_name, lead.city, last_email.subject, step=1)
                    queue_email(
                        lead_id=lead.id,
                        recipient_email=contact.email,
                        sender_account=last_email.sender_account,
                        subject=fu_content["subject"],
                        body_text=fu_content["body_text"],
                        body_html=None,
                        email_type="FOLLOW_UP_1"
                    )
                    queued_count += 1
                    print(f"[FollowUp] Queued Follow-Up #1 for Lead #{lead.id} ({lead.business_name})")
                    
        # 2. Follow-Up #2 (4 days after Follow-Up #1 / 7 days total)
        fu2_threshold = now - timedelta(days=settings.SECOND_FOLLOW_UP_DAYS)
        eligible_for_fu2 = session.query(Lead).filter(
            Lead.status == "FOLLOW_UP_1"
        ).all()
        
        for lead in eligible_for_fu2:
            last_email = session.query(EmailCampaign).filter(
                EmailCampaign.lead_id == lead.id,
                EmailCampaign.email_type == "FOLLOW_UP_1",
                EmailCampaign.status == "SENT"
            ).order_by(EmailCampaign.sent_at.desc()).first()
            
            if last_email and last_email.sent_at and last_email.sent_at <= fu2_threshold:
                contact = session.query(ContactInfo).filter(ContactInfo.lead_id == lead.id).first()
                if contact:
                    fu_content = generate_followup_email(lead.business_name, lead.city, last_email.subject, step=2)
                    queue_email(
                        lead_id=lead.id,
                        recipient_email=contact.email,
                        sender_account=last_email.sender_account,
                        subject=fu_content["subject"],
                        body_text=fu_content["body_text"],
                        body_html=None,
                        email_type="FOLLOW_UP_2"
                    )
                    queued_count += 1
                    print(f"[FollowUp] Queued Follow-Up #2 (Final) for Lead #{lead.id} ({lead.business_name})")
                    
        return queued_count
    finally:
        session.close()
