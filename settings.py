import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # AI API Keys (Supports OpenAI ChatGPT and Google Gemini)
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")
    GEMINI_API_KEY: str = Field(default="", env="GEMINI_API_KEY")
    
    # Operation Mode
    DRY_RUN: bool = Field(default=False, env="DRY_RUN")
    SEND_DURING_BUSINESS_HOURS_ONLY: bool = Field(default=True, env="SEND_DURING_BUSINESS_HOURS_ONLY")
    
    # Redesign Offer Details
    REDESIGN_OFFER_PRICE: int = Field(default=500, env="REDESIGN_OFFER_PRICE")
    SENDER_NAME: str = Field(default="Tushar", env="SENDER_NAME")
    SENDER_TITLE: str = Field(default="", env="SENDER_TITLE")
    
    # 4 Gmail Accounts Login Credentials
    GMAIL_ACCOUNT_1_USER: str = Field(default="tusharkumarbusinessgrowth@gmail.com", env="GMAIL_ACCOUNT_1_USER")
    GMAIL_ACCOUNT_1_PASS: str = Field(default="erkviudcqmhyrnhn", env="GMAIL_ACCOUNT_1_PASS")
    
    GMAIL_ACCOUNT_2_USER: str = Field(default="", env="GMAIL_ACCOUNT_2_USER")
    GMAIL_ACCOUNT_2_PASS: str = Field(default="", env="GMAIL_ACCOUNT_2_PASS")
    
    GMAIL_ACCOUNT_3_USER: str = Field(default="", env="GMAIL_ACCOUNT_3_USER")
    GMAIL_ACCOUNT_3_PASS: str = Field(default="", env="GMAIL_ACCOUNT_3_PASS")
    
    GMAIL_ACCOUNT_4_USER: str = Field(default="", env="GMAIL_ACCOUNT_4_USER")
    GMAIL_ACCOUNT_4_PASS: str = Field(default="", env="GMAIL_ACCOUNT_4_PASS")
    
    # Quotas & Rate Limits
    DAILY_LIMIT_PER_ACCOUNT: int = Field(default=25, env="DAILY_LIMIT_PER_ACCOUNT")
    MIN_DELAY_BETWEEN_EMAILS_SEC: int = Field(default=120, env="MIN_DELAY_BETWEEN_EMAILS_SEC")
    MAX_DELAY_BETWEEN_EMAILS_SEC: int = Field(default=360, env="MAX_DELAY_BETWEEN_EMAILS_SEC")
    
    # Follow-up rules (in days)
    FIRST_FOLLOW_UP_DAYS: int = Field(default=3, env="FIRST_FOLLOW_UP_DAYS")
    SECOND_FOLLOW_UP_DAYS: int = Field(default=7, env="SECOND_FOLLOW_UP_DAYS")
    
    # Database Path
    DATABASE_PATH: str = Field(default="data/outreach_agent.db", env="DATABASE_PATH")
    
    # High-Ticket Target Niches
    BUSINESS_NICHES: List[str] = [
        "cosmetic dentist dental implants clinic",
        "carpenter custom woodworking cabinets",
        "solar panel installation solar agency",
        "roofing contractor roof replacement",
        "hvac heating and air conditioning repair",
        "plumbing contractor water damage",
        "kitchen and bathroom remodeling contractor",
        "personal injury attorney law firm",
        "chiropractor chiropractic wellness center",
        "electrician electrical contractor",
        "commercial landscaping hardscaping",
        "tree removal and arborist service",
        "auto collision repair body shop",
        "commercial cleaning janitorial services",
        "pool installation and repair contractor"
    ]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
