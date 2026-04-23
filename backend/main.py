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

from database import (
    init_db, init_subscribers_table, get_cached, save_cache,
    init_sent_alerts_table, init_rate_limits_table, init_jobs_table,
    check_rate_limit_db, upsert_job, get_job_by_id,
    create_subscriber, get_subscriber_by_email, delete_subscriber,
    get_active_subscribers, update_subscriber_alert_count,
    update_subscriber_keywords, get_all_cache
)
from adzuna import fetch_jobs_from_adzuna
from email_service import send_email, format_job_alert_email, format_welcome_email

# Configure logging for internal errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

@app.on_event("startup")
async def startup():
    await init_db()
    await init_subscribers_table()
    await init_sent_alerts_table()
    await init_rate_limits_table()
    await init_jobs_table()

def get_daily_cache_key(keyword: str, days_ago: int) -> str:
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    raw = f"{keyword}_{days_ago}_{today_str}"
    return hashlib.md5(raw.encode()).hexdigest()

@app.middleware("http")
async def apply_rate_limit(request: Request, call_next):
    """Apply SQLite-backed rate limiting to POST endpoints."""
    if request.method == "POST" and request.url.path in ("/search", "/subscribe", "/_cron/send-alerts"):
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

    total = len(unique_jobs)
    paginated = unique_jobs[req.offset : req.offset + req.limit]

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
