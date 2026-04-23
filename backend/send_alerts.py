"""
Daily subscriber alert cron job.
Run this daily via Render cron job or system cron.
Usage: python send_alerts.py

Sends job alerts to all active subscribers based on their saved preferences.
Deduplicates so subscribers never see the same job twice.
"""
import asyncio
import json
import os
import sys

# Add the backend directory to path if running from root
sys.path.insert(0, os.path.dirname(__file__))

from adzuna import fetch_jobs_from_adzuna
from database import (
    init_db, init_subscribers_table, get_active_subscribers,
    update_subscriber_alert_count,
    init_sent_alerts_table, is_alert_sent, mark_alert_sent,
    prune_old_sent_alerts,
)
from email_service import send_email, format_job_alert_email


async def send_daily_alerts():
    """Send job alerts to all active subscribers."""
    print("[ALERTS] Starting daily alert run...")

    await init_db()
    await init_subscribers_table()
    await init_sent_alerts_table()
    await init_jobs_table()

    # Keep DB lean — prune alerts older than 30 days
    await prune_old_sent_alerts(days=30)

    subscribers = await get_active_subscribers()
    print(f"[ALERTS] Found {len(subscribers)} active subscribers")

    if not subscribers:
        print("[ALERTS] No subscribers to notify. Done.")
        return

    successful = 0
    failed = 0
    skipped = 0

    for sub in subscribers:
        try:
            print(f"\n[ALERTS] Processing {sub['email']} ({sub['name']})...")

            keywords = json.loads(sub["keywords"])
            location = sub["location"]
            days_ago = sub["days_ago"]
            min_salary = sub.get("min_salary")

            # Fetch jobs using existing Adzuna integration
            all_jobs = []
            seen_ids = set()

            for keyword in keywords:
                try:
                    jobs = await fetch_jobs_from_adzuna(keyword, days_ago)
                    for job in jobs:
                        if job["id"] not in seen_ids:
                            seen_ids.add(job["id"])
                            all_jobs.append(job)
                except Exception as e:
                    print(f"  [ERROR] Failed to fetch '{keyword}': {e}")

            # Sort by whitelist match first, then date
            all_jobs.sort(key=lambda j: (not j.get("whitelist_match", False), j.get("created", "")), reverse=True)

            # Apply min_salary filter if set
            if min_salary:
                all_jobs = [
                    j for j in all_jobs
                    if (j.get("salary_max") and j["salary_max"] >= min_salary) or
                       (j.get("salary_min") and j["salary_min"] >= min_salary)
                ]

            # DEDUPLICATION: Filter out jobs already sent to this subscriber
            new_jobs = []
            for job in all_jobs:
                if not await is_alert_sent(sub["id"], job["id"]):
                    new_jobs.append(job)

            if not new_jobs:
                print(f"  [ALERTS] No new jobs for {sub['email']} (all already sent)")
                skipped += 1
                continue

            print(f"  [ALERTS] {len(new_jobs)} new jobs for {sub['email']} (filtered {len(all_jobs) - len(new_jobs)} duplicates)")

            # Create and send email
            html = format_job_alert_email(sub["name"], new_jobs, sub["email"])
            subject = f"🔥 {len(new_jobs)} new UK Finance Job{'s' if len(new_jobs) > 1 else ''} for you"

            sent = await send_email(
                to=sub["email"],
                subject=subject,
                html_body=html
            )

            if sent:
                # Mark every job in this alert as sent so we never send it again
                for job in new_jobs:
                    await mark_alert_sent(sub["id"], job["id"])
                await update_subscriber_alert_count(sub["id"])
                print(f"  [ALERTS] Sent alert to {sub['email']} with {len(new_jobs)} jobs")
                successful += 1
            else:
                print(f"  [ALERTS] Email delivery failed for {sub['email']}")
                failed += 1

        except Exception as e:
            print(f"  [ERROR] Exception processing {sub['email']}: {e}")
            failed += 1

    print(f"\n[ALERTS] Daily alert run complete: {successful} sent, {failed} failed, {skipped} skipped (no new jobs)")


if __name__ == "__main__":
    asyncio.run(send_daily_alerts())
