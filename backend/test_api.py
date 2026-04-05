"""
CLI test: hit the backend directly to verify Adzuna integration and caching logic.
Run with: python test_api.py
"""
import asyncio
import json
import hashlib
from datetime import datetime

async def test_backend():
    """Test the fetch-vs-cache decision tree directly."""
    from database import init_db, get_cached, save_cache
    from adzuna import fetch_jobs_from_adzuna
    
    print("=" * 60)
    print("UK Finance Job Aggregator - API Integration Test")
    print("=" * 60)

    # Init DB
    await init_db()
    print("[OK] Database initialized")

    keyword = "Senior Software Engineer"
    days_ago = 7
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    raw = f"{keyword}_{days_ago}_{today_str}"
    cache_key = hashlib.md5(raw.encode()).hexdigest()

    # Step 1: Check cache (should miss first time)
    cached = await get_cached(cache_key)
    if cached:
        print(f"[CACHE HIT] Returning {len(json.loads(cached['content']))} cached jobs for '{keyword}'")
        return json.loads(cached["content"])
    else:
        print(f"[CACHE MISS] Fetching from Adzuna API for '{keyword}'...")

    # Step 2: Fetch from API
    try:
        jobs = await fetch_jobs_from_adzuna(keyword, days_ago)
    except Exception as e:
        print(f"[ERROR] API call failed: {e}")
        return []

    print(f"  -> Fetched {len(jobs)} jobs total")
    
    if not jobs:
        print("[INFO] No matching jobs found (check whitelist/API)")
        return jobs

    # Filter stats
    whitelist_count = sum(1 for j in jobs if j.get("whitelist_match"))
    print(f"  -> {whitelist_count} whitelist matches, {len(jobs) - whitelist_count} finance-relevant")

    # Show first 5 results
    print("\n  Top Results:")
    for i, job in enumerate(jobs[:5]):
        salary = ""
        if job.get("salary_min") and job.get("salary_max"):
            salary = f" | £{int(job['salary_min']/1000)}k-£{int(job['salary_max']/1000)}k"
        elif job.get("salary_min"):
            salary = f" | £{int(job['salary_min']/1000)}k"
        wl_tag = "⭐" if job.get("whitelist_match") else ""
        print(f"    {i+1}. {job['title'][:50]} | {job['company']} | {job['location']}{salary} {wl_tag}")

    # Save to cache
    await save_cache(cache_key, json.dumps(jobs))
    print(f"\n[OK] Saved to cache (key: {cache_key[:8]}...)")

    # Step 3: Verify cache hit on second call
    cached_again = await get_cached(cache_key)
    if cached_again:
        print(f"[OK] Cache hit confirmed: fetched_at={cached_again['fetched_at']}")

    print("\n" + "=" * 60)
    print("Test complete!")
    return jobs

if __name__ == "__main__":
    asyncio.run(test_backend())
