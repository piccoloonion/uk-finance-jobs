from fastapi import FastAPI, HTTPException, Query, Request
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

from database import init_db, get_cached, save_cache
from adzuna import fetch_jobs_from_adzuna

# Configure logging for internal errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="UK Finance Job Aggregator")

# SECURITY FIX 1: Lock CORS to specific origins (not wildcard)
# Add your production domain here before deploying
import os as _os
CORS_ORIGINS_ENV = _os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_ENV.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# SECURITY FIX 4: Simple in-memory rate limiter
class RateLimiter:
    """Rate limiter: max_requests per window_seconds per IP."""
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        # Clean old entries
        self.requests[client_ip] = [
            t for t in self.requests[client_ip]
            if now - t < self.window_seconds
        ]
        if len(self.requests[client_ip]) >= self.max_requests:
            return False
        self.requests[client_ip].append(now)
        return True

rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

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
                raise ValueError(f"Keyword '{kw[:20]}...' exceeds 100 character limit")
            # Strip dangerous characters
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

@app.on_event("startup")
async def startup():
    await init_db()

def get_daily_cache_key(keyword: str, days_ago: int) -> str:
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    raw = f"{keyword}_{days_ago}_{today_str}"
    return hashlib.md5(raw.encode()).hexdigest()

@app.options("/search")
async def search_options():
    return ""

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

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
                raise HTTPException(status_code=502, detail=f"API error for '{keyword}': {str(e)}")
            
            await save_cache(cache_key, json.dumps(jobs_data))
            cache_info[keyword] = "fetched"

        all_jobs.extend(jobs_data)

    seen_ids = set()
    unique_jobs = []
    for job in all_jobs:
        if job["id"] not in seen_ids:
            seen_ids.add(job["id"])
            unique_jobs.append(job)

    unique_jobs.sort(key=lambda j: (not j.get("whitelist_match", False), j.get("created", "")), reverse=True)

    return unique_jobs

@app.get("/cache-stats")
async def cache_stats():
    from database import DB_PATH
    import aiosqlite
    
    info = {}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT cache_key, fetched_at FROM job_cache") as cursor:
            async for row in cursor:
                info[row[0]] = row[1]
    
    return {
        "total_cached_queries": len(info),
        "cached_at": info
    }
