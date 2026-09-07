import sys
import os
import io

# Force UTF-8 stdout on Windows terminals
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
import subprocess
from rich.console import Console
from rich.table import Table

from config.settings import settings
from database.db_manager import init_db, get_stats, SessionLocal
from database.models import CityProgress, Lead, EmailCampaign, InboxMessage
from modules.sender import GmailAccountManager
from daemon import (
    job_discover_and_audit, job_send_queued_emails, job_monitor_inbox,
    job_check_follow_ups, start_daemon
)

console = Console(force_terminal=True, legacy_windows=False)

def show_banner():
    banner = """
===============================================================
       24/7 AUTONOMOUS OUTREACH & WEBSITE AUDIT AGENT          
   East-to-West US City Traverser | $500 Website Redesign Pitch
===============================================================
    """
    console.print(f"[bold cyan]{banner}[/bold cyan]")

def display_stats():
    stats = get_stats()
    account_mgr = GmailAccountManager()
    acc_statuses = account_mgr.get_all_accounts_status()
    
    table = Table(title="Pipeline Metrics & Conversion Funnel", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Count / Value", style="green", justify="right")
    
    table.add_row("US Cities in Route", str(stats["total_cities"]))
    table.add_row("Cities Scanned so far", str(stats["scanned_cities"]))
    table.add_row("Total Businesses Discovered", str(stats["total_leads"]))
    table.add_row("Outdated Websites Detected", str(stats["outdated_leads"]))
    table.add_row("Modern Websites (Skipped)", str(stats["modern_leads"]))
    table.add_row("Contact Emails Harvested", str(stats["emails_found"]))
    table.add_row("Emails Sent (Lifetime)", str(stats["emails_sent"]))
    table.add_row("Emails Sent Today", f"{stats['today_sent']} / 60")
    table.add_row("Prospect Replies Received", str(stats["replies_received"]))
    table.add_row("Meetings / Leads Booked", str(stats["meetings_booked"]))
    
    console.print(table)
    
    # Account status table
    acc_table = Table(title="4x Gmail Accounts Capacity (15/day each)", show_header=True, header_style="bold yellow")
    acc_table.add_column("Account Email", style="white")
    acc_table.add_column("Sent Today", justify="center")
    acc_table.add_column("Daily Limit", justify="center")
    acc_table.add_column("Remaining Quota", justify="center", style="bold green")
    
    for s in acc_statuses:
        acc_table.add_row(
            s["account"],
            str(s["sent_today"]),
            str(s["daily_limit"]),
            str(s["remaining"])
        )
    console.print(acc_table)
    
    mode_text = "[bold red]LIVE SENDING ACTIVE[/bold red]" if not settings.DRY_RUN else "[bold yellow]DRY RUN (Simulated Safety Mode)[/bold yellow]"
    console.print(f"Current Operational Mode: {mode_text}\n")

def main():
    parser = argparse.ArgumentParser(description="24/7 Autonomous Client Hunter Agent")
    parser.add_argument("command", choices=["run-daemon", "scan-now", "send-batch", "check-inbox", "stats", "dashboard"], help="Command to execute")
    
    if len(sys.argv) == 1:
        show_banner()
        parser.print_help()
        sys.exit(1)
        
    args = parser.parse_args()
    init_db()
    
    if args.command == "run-daemon":
        show_banner()
        display_stats()
        console.print("[bold green]Starting 24/7 continuous daemon process... (Press Ctrl+C to stop)[/bold green]")
        start_daemon()
    elif args.command == "scan-now":
        show_banner()
        console.print("[cyan]Triggering manual Discovery & Audit cycle for next East-to-West city...[/cyan]")
        job_discover_and_audit()
        display_stats()
    elif args.command == "send-batch":
        show_banner()
        console.print("[cyan]Triggering email queue dispatcher...[/cyan]")
        job_send_queued_emails()
        display_stats()
    elif args.command == "check-inbox":
        show_banner()
        console.print("[cyan]Checking Gmail inboxes for incoming replies...[/cyan]")
        job_monitor_inbox()
        display_stats()
    elif args.command == "stats":
        show_banner()
        display_stats()
    elif args.command == "dashboard":
        console.print("[bold green]Launching Interactive Web Dashboard on http://localhost:8501 ...[/bold green]")
        subprocess.run([sys.executable, "-m", "streamlit", "run", "dashboard/app.py"])

if __name__ == "__main__":
    main()
