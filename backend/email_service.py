"""Email service using Resend API for job alert emails."""
import os
import html
from urllib.parse import urlparse
import httpx

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "alerts@ukfinancejobs.co.uk")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def _safe_href(url: str) -> str:
    """Validate URL is http/https only. Returns safe URL or '#'. """
    try:
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https'):
            return html.escape(url)
    except Exception:
        pass
    return "#"


def _safe(text: str) -> str:
    """HTML-escape text for safe inclusion in email body."""
    return html.escape(str(text), quote=True)


async def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send an email via Resend API."""
    if not RESEND_API_KEY:
        print("[EMAIL] No RESEND_API_KEY set, skipping send")
        return False

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"UK Finance Jobs <{RESEND_FROM_EMAIL}>",
                "to": [to],
                "subject": subject,
                "html": html_body,
            },
        )

        if resp.status_code in (200, 201):
            print(f"[EMAIL] Sent to {to}: {subject}")
            return True
        else:
            print(f"[EMAIL] Failed to send to {to}: {resp.status_code} {resp.text}")
            return False


def format_job_alert_email(name: str, jobs: list, unsubscribe_email: str) -> str:
    """Format a job alert as HTML email. All external data is escaped."""
    job_rows = ""
    for job in jobs:
        salary = ""
        if job.get("salary_min") and job.get("salary_max"):
            salary = f"&#163;{job['salary_min']:,.0f} - &#163;{job['salary_max']:,.0f}"
        elif job.get("salary_min"):
            salary = f"From &#163;{job['salary_min']:,.0f}"
        elif job.get("salary_max"):
            salary = f"Up to &#163;{job['salary_max']:,.0f}"
        else:
            salary = "Salary not disclosed"

        badge = ""
        if job.get("whitelist_match"):
            badge = '<span style="background:#10b981;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;margin-left:8px;">TOP BANK</span>'

        safe_url = _safe_href(job.get('url', ''))
        safe_title = _safe(job.get('title', 'Untitled'))
        safe_company = _safe(job.get('company', 'Unknown'))
        safe_location = _safe(job.get('location', 'UK'))
        safe_contract = _safe(job.get('contract_type', 'Permanent'))
        safe_created = _safe(job.get('created', '')[:10])

        job_rows += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;background:#fff;">
            <div style="margin-bottom:8px;">
                <a href="{safe_url}" target="_blank" style="font-size:16px;font-weight:600;color:#1d4ed8;text-decoration:none;">
                    {safe_title}
                </a>
                {badge}
            </div>
            <div style="font-size:14px;color:#374151;margin-bottom:6px;">
                <strong>{safe_company}</strong> &middot; {safe_location}
            </div>
            <div style="font-size:13px;color:#6b7280;">
                {salary} &middot; {safe_contract}
                {'&middot; Posted ' + safe_created if safe_created else ''}
            </div>
            <div style="margin-top:10px;">
                <a href="{safe_url}" target="_blank" style="background:#2563eb;color:#fff;padding:6px 16px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:500;">
                    View Job &rarr;
                </a>
            </div>
        </div>
        """

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background:#1e3a5f;color:#fff;padding:24px;border-radius:12px 12px 0 0;text-align:center;">
            <h1 style="margin:0;font-size:22px;">UK Finance Jobs Alert</h1>
            <p style="margin:8px 0 0;opacity:0.8;font-size:14px;">Hi {_safe(name)}, here are your matched roles today</p>
        </div>

        <div style="background:#f9fafb;padding:24px;border-radius:0 0 12px 12px;">
            <p style="font-size:14px;color:#374151;margin-bottom:16px;">
                <strong>{len(jobs)} new role{'s' if len(jobs) != 1 else ''}</strong> matched your criteria.
            </p>

            {job_rows}

            <div style="text-align:center;margin-top:20px;">
                <a href="{FRONTEND_URL}" target="_blank" style="background:#10b981;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">
                    Search All Jobs &rarr;
                </a>
            </div>
        </div>

        <div style="text-align:center;margin-top:20px;padding:16px;font-size:12px;color:#9ca3af;">
            <p>You&rsquo;re receiving this because you subscribed at UK Finance Jobs.</p>
            <p>
                <a href="{FRONTEND_URL}/unsubscribe?email={_safe(unsubscribe_email)}" style="color:#6b7280;text-decoration:underline;">
                    Unsubscribe
                </a>
                &nbsp;|&nbsp;
                <a href="{FRONTEND_URL}" style="color:#6b7280;text-decoration:underline;">
                    Manage Preferences
                </a>
            </p>
        </div>
    </div>
    """
    return html


def format_welcome_email(name: str) -> str:
    """Format welcome confirmation email."""
    safe_name = _safe(name)
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background:#1e3a5f;color:#fff;padding:24px;border-radius:12px;text-align:center;">
            <h1 style="margin:0;font-size:22px;">Welcome to UK Finance Jobs! 🎉</h1>
        </div>
        <div style="background:#f9fafb;padding:24px;border-radius:12px;margin-top:12px;">
            <p style="font-size:15px;color:#374151;">Hi {safe_name},</p>
            <p style="font-size:14px;color:#4b5563;line-height:1.6;">
                You&rsquo;re all set! We&rsquo;ll send you daily job alerts matching your criteria.
                Your first alert will arrive within 24 hours.
            </p>
            <p style="font-size:14px;color:#4b5563;line-height:1.6;">
                <strong>Upgrade to Pro (&#163;5/month)</strong> for:
            </p>
            <ul style="font-size:14px;color:#4b5563;line-height:2;">
                <li>Daily alerts (free = weekly)</li>
                <li>Unlimited keyword filters</li>
                <li>Salary-based filtering</li>
                <li>Priority new job notifications</li>
            </ul>
            <p style="text-align:center;margin-top:20px;">
                <a href="{FRONTEND_URL}" style="background:#2563eb;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">
                    Visit the Job Board &rarr;
                </a>
            </p>
        </div>
    </div>
    """
    return html
