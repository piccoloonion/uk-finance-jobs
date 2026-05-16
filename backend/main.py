from fastapi import FastAPI, HTTPException, Query, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from typing import List, Optional
import json
import hashlib
import logging
from datetime import datetime
from collections import defaultdict
import time
import os
import uuid
import stripe

from database import (
    init_db, init_subscribers_table, get_cached, save_cache,
    init_sent_alerts_table, init_rate_limits_table, init_jobs_table,
    init_sponsored_jobs_table,
    check_rate_limit_db, upsert_job, get_job_by_id,
    create_subscriber, get_subscriber_by_email, delete_subscriber,
    get_active_subscribers, update_subscriber_alert_count,
    update_subscriber_keywords, get_all_cache,
    create_sponsored_job, get_active_sponsored_jobs,
    get_sponsored_job_by_session, activate_sponsored_job, expire_stale_sponsored_jobs
)
from adzuna import fetch_jobs_from_adzuna
from email_service import send_email, format_job_alert_email, format_welcome_email

# Configure logging for internal errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Stripe configuration
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

SPONSOR_PRICE_PENCE = 4900  # £49.00 in pence

app = FastAPI(title="UK Finance Job Aggregator")

# SECURITY FIX 1: Lock CORS to specific origins (not wildcard)
CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_ENV.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

class JobResponse(BaseModel):
    id: Optional[str] = None
    title: str
    company: str
    location: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_predicted: bool = False
    created: str
    description: str = ""
    url: str = ""
    category: str = ""
    whitelist_match: bool = False
    contract_type: Optional[str] = None

class SearchRequest(BaseModel):
    keywords: List[str] = ["Senior Software Engineer", "Senior Data Engineer"]
    days_ago: int = 7
    limit: int = 50
    offset: int = 0

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one keyword is required")
        if len(v) > 10:
            raise ValueError("Maximum 10 keywords allowed")
        cleaned = []
        for kw in v:
            kw = kw.strip()
            if not kw:
                continue
            if len(kw) > 100:
                raise ValueError(f"Keyword too long")
            kw = kw.replace("<", "").replace(">", "").replace('"', "").replace("'", "")
            cleaned.append(kw)
        if not cleaned:
            raise ValueError("At least one valid keyword is required")
        return cleaned

    @field_validator("days_ago")
    @classmethod
    def validate_days_ago(cls, v: int) -> int:
        if v < 1:
            raise ValueError("days_ago must be at least 1")
        if v > 30:
            raise ValueError("days_ago cannot exceed 30")
        return v

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v < 1:
            return 50
        if v > 100:
            return 100
        return v

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 0:
            return 0
        return v

class SubscribeRequest(BaseModel):
    email: str
    name: str = ""
    keywords: List[str] = ["Software Engineer"]
    location: str = "London"
    days_ago: int = 7
    min_salary: int = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v.lower().strip()

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one keyword is required")
        return [kw.strip() for kw in v if kw.strip()]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip()[:100] if v else "Subscriber"

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: str) -> str:
        return v.strip()[:50] or "London"

class UnsubscribeRequest(BaseModel):
    email: str

class UpdatePreferencesRequest(BaseModel):
    email: str
    keywords: List[str] = None
    location: str = None
    days_ago: int = None
    min_salary: int = None

class SponsorCheckoutRequest(BaseModel):
    job_title: str
    company_name: str
    job_url: str
    contact_email: str

    @field_validator("contact_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v.lower().strip()

    @field_validator("job_title")
    @classmethod
    def validate_job_title(cls, v: str) -> str:
        if not v or len(v.strip()) < 2:
            raise ValueError("Job title is required")
        return v.strip()[:200]

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v: str) -> str:
        if not v or len(v.strip()) < 1:
            raise ValueError("Company name is required")
        return v.strip()[:200]

    @field_validator("job_url")
    @classmethod
    def validate_job_url(cls, v: str) -> str:
        if not v.startswith("http://") and not v.startswith("https://"):
            raise ValueError("Invalid URL — must start with http:// or https://")
        return v.strip()[:500]

class SponsoredJobResponse(BaseModel):
    id: str
    company_name: str
    job_title: str
    job_url: str
    contact_email: str
    amount_paid: float
    created_at: str
    expires_at: str

@app.on_event("startup")
async def startup():
    await init_db()
    await init_subscribers_table()
    await init_sent_alerts_table()
    await init_rate_limits_table()
    await init_jobs_table()
    await init_sponsored_jobs_table()

def get_daily_cache_key(keyword: str, days_ago: int) -> str:
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    raw = f"{keyword}_{days_ago}_{today_str}"
    return hashlib.md5(raw.encode()).hexdigest()

@app.middleware("http")
async def apply_rate_limit(request: Request, call_next):
    """Apply SQLite-backed rate limiting to POST endpoints."""
    if request.method == "POST" and request.url.path in ("/search", "/subscribe", "/_cron/send-alerts", "/sponsor-checkout", "/sponsored-webhook"):
        client_ip = request.client.host if request.client else "unknown"
        if not await check_rate_limit_db(client_ip, max_requests=10, window_seconds=60):
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": "60"}
            )
    response = await call_next(request)
    return response

@app.post("/search", response_model=List[JobResponse])
async def search_jobs(req: SearchRequest):
    all_jobs = []
    cache_info = {}

    for keyword in req.keywords:
        cache_key = get_daily_cache_key(keyword, req.days_ago)
        
        cached = await get_cached(cache_key)
        if cached:
            jobs_data = json.loads(cached["content"])
            cache_info[keyword] = "cache_hit"
        else:
            try:
                jobs_data = await fetch_jobs_from_adzuna(keyword, req.days_ago)
            except Exception as e:
                logger.error(f"API error for '{keyword}': {e}")
                raise HTTPException(status_code=502, detail="Job service temporarily unavailable.")
            
            await save_cache(cache_key, json.dumps(jobs_data))
            cache_info[keyword] = "fetched"

        all_jobs.extend(jobs_data)

    seen_ids = set()
    unique_jobs = []
    for job in all_jobs:
        if job["id"] not in seen_ids:
            seen_ids.add(job["id"])
            unique_jobs.append(job)
            # Persist each job for detail-page lookups
            try:
                await upsert_job(job)
            except Exception as e:
                logger.warning(f"Failed to upsert job {job.get('id')}: {e}")

    unique_jobs.sort(key=lambda j: (not j.get("whitelist_match", False), j.get("created", "")), reverse=True)

    # Fetch active sponsored jobs to prepend
    try:
        sponsored = await get_active_sponsored_jobs()
    except Exception as e:
        logger.warning(f"Failed to fetch sponsored jobs: {e}")
        sponsored = []

    # Prepend sponsored jobs (they sort first), then whitelist-match, then by date
    sponsored_ids = {s["id"] for s in sponsored}
    sponsored_as_jobs = [
        {
            "id": s["id"],
            "title": s["job_title"],
            "company": s["company_name"],
            "location": "",
            "salary_min": None,
            "salary_max": None,
            "salary_predicted": False,
            "created": s["created_at"],
            "description": "",
            "url": s["job_url"],
            "category": "sponsored",
            "whitelist_match": False,
            "contract_type": None,
            "_sponsored": True,
        }
        for s in sponsored
    ]

    # Filter out any job that matches a sponsored ID (avoid dupes)
    unique_jobs = [j for j in unique_jobs if j["id"] not in sponsored_ids]

    total = len(sponsored_as_jobs) + len(unique_jobs)
    combined = sponsored_as_jobs + unique_jobs
    paginated = combined[req.offset : req.offset + req.limit]

    # Return paginated slice; client can use total + offset/limit for UI
    response = JSONResponse(content=paginated)
    response.headers["X-Total-Count"] = str(total)
    return response

@app.get("/job/{job_id}")
async def get_job_detail(job_id: str):
    """Fetch a single job by ID for detail pages."""
    job = await get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

# --- Cron endpoint for external schedulers (e.g. cron-job.org) ---

@app.post("/_cron/send-alerts")
async def cron_send_alerts(secret: str = Header(..., alias="x-cron-secret")):
    """Trigger daily alerts via external cron service. Requires CRON_SECRET env var."""
    expected = os.getenv("CRON_SECRET", "")
    if not expected or secret != expected:
        raise HTTPException(status_code=401, detail="Invalid cron secret")
    
    from send_alerts import send_daily_alerts
    await send_daily_alerts()
    return {"ok": True, "message": "Alerts processed"}

# --- Subscription endpoints ---

@app.post("/subscribe", status_code=201)
async def subscribe(req: SubscribeRequest):
    existing = await get_subscriber_by_email(req.email)
    if existing:
        if existing["active"]:
            return {"message": "Already subscribed", "subscribed": True, "email": req.email}
        else:
            await update_subscriber_keywords(
                req.email,
                json.dumps(req.keywords),
                req.location,
                req.days_ago,
                req.min_salary
            )
            return {"message": "Resubscribed successfully", "subscribed": True, "email": req.email}

    success = await create_subscriber(
        email=req.email,
        name=req.name,
        keywords=json.dumps(req.keywords),
        location=req.location,
        days_ago=req.days_ago,
        min_salary=req.min_salary
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to subscribe.")

    # Send welcome email (non-blocking)
    try:
        await send_email(
            to=req.email,
            subject="Welcome to UK Finance Jobs alerts!",
            html_body=format_welcome_email(req.name or "Subscriber")
        )
    except Exception as e:
        logger.warning(f"Welcome email failed: {e}")

    return {"message": "Subscribed successfully", "subscribed": True, "email": req.email}

@app.post("/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest):
    await delete_subscriber(req.email)
    return {"message": "Unsubscribed successfully", "subscribed": False}

@app.post("/update-preferences")
async def update_preferences(req: UpdatePreferencesRequest):
    subscriber = await get_subscriber_by_email(req.email)
    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    keywords = json.loads(subscriber["keywords"]) if req.keywords is None else req.keywords
    location = subscriber["location"] if req.location is None else req.location
    days_ago = subscriber["days_ago"] if req.days_ago is None else req.days_ago
    min_salary = subscriber["min_salary"] if req.min_salary is None else req.min_salary

    await update_subscriber_keywords(
        req.email,
        json.dumps(keywords),
        location,
        days_ago,
        min_salary
    )

    return {"message": "Preferences updated", "email": req.email}

@app.get("/subscriber/{email}")
async def get_subscriber(email: str):
    subscriber = await get_subscriber_by_email(email)
    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    subscriber["keywords"] = json.loads(subscriber["keywords"])
    return subscriber

@app.get("/cache-stats")
async def cache_stats():
    info = {}
    rows = await get_all_cache()
    for row in rows:
        info[row[0]] = row[1]
    
    return {
        "total_cached_queries": len(info),
        "cached_at": info
    }

@app.get("/stats")
async def stats():
    """Quick stats on subscribers."""
    free_subs = await get_active_subscribers(tier="free")
    pro_subs = await get_active_subscribers(tier="pro")
    return {
        "free_subscribers": len(free_subs),
        "pro_subscribers": len(pro_subs),
        "total_subscribers": len(free_subs) + len(pro_subs),
    }

# ─── Sponsorship endpoints ───

@app.post("/sponsor-checkout")
async def sponsor_checkout(req: SponsorCheckoutRequest):
    """Create a Stripe Checkout session for job sponsorship (£49)."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured — set STRIPE_SECRET_KEY")

    sponsor_id = str(uuid.uuid4())
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "gbp",
                    "product_data": {
                        "name": f"Sponsored job: {req.job_title} at {req.company_name}",
                        "description": "30-day featured job listing on UK Finance Jobs",
                    },
                    "unit_amount": SPONSOR_PRICE_PENCE,
                },
                "quantity": 1,
            }],
            customer_email=req.contact_email,
            metadata={
                "sponsor_id": sponsor_id,
                "job_title": req.job_title,
                "company_name": req.company_name,
                "job_url": req.job_url,
            },
            success_url=f"{frontend_url}/?sponsor=success",
            cancel_url=f"{frontend_url}/?sponsor=cancel",
        )

        # Store sponsorship record (not active yet — activates on webhook)
        await create_sponsored_job(
            id=sponsor_id,
            company_name=req.company_name,
            job_title=req.job_title,
            job_url=req.job_url,
            contact_email=req.contact_email,
            stripe_session_id=session.id,
            is_active=0,
        )

        return {"checkout_url": session.url, "session_id": session.id}

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=502, detail="Payment service error. Please try again.")
    except Exception as e:
        logger.error(f"Sponsor checkout error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@app.get("/sponsored", response_model=List[SponsoredJobResponse])
async def list_sponsored():
    """Return active sponsored jobs (paid + not expired)."""
    await expire_stale_sponsored_jobs()
    jobs = await get_active_sponsored_jobs()
    return jobs


@app.post("/sponsored-webhook")
async def sponsored_webhook(request: Request):
    """Handle Stripe checkout.session.completed events."""
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session.get("id")

        if session.get("payment_status") == "paid":
            await activate_sponsored_job(session_id)
            logger.info(f"Sponsored job activated for session {session_id}")
        else:
            logger.info(f"Session {session_id} completed but not yet paid")

    return {"ok": True}
