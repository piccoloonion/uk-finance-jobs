import aiohttp
import os
from typing import List, Dict
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("ADZUNA_APP_ID", "")
APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

FINANCE_WHITELIST = {
    "hsbc", "barclays", "revolut", "monzo", "starling", "lloyds",
    "natwest", "standard chartered", "jpmorgan", "goldman sachs",
    "fidelity", "bloomberg", "wise", "coinbase", "morgan stanley",
    "schroders", "abrdn", "aviva", "legal & general", "prudential",
    "metro bank", "santander uk", "nationwide", "tide", "oaknorth",
    "10x banking", "form3", "clearmatics", "chainalysis", "elliptic",
    "citigroup", "deutsche bank", "ubs", "credit suisse", "investec",
    "stifel", "jefferies", "houlihan lokey", "pimco", "blackrock",
    "zopa", "funding circle", "marketinvoice", "iwoca"
}

FINANCE_KEYWORDS = [
    "finance", "bank", "fintech", "trading", "hedge",
    "asset management", "insurance", "pension", "investment",
    "financial", "capital", "broker", "equity", "credit",
    "quant", "quantitative", "risk", "compliance", "regtech"
]


def parse_created(created_str: str) -> datetime:
    """Parse Adzuna's created date (ISO format)."""
    try:
        # Handle formats like: "2026-03-26T11:47:03Z"
        return datetime.fromisoformat(created_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def is_within_days(created_str: str, days_ago: int) -> bool:
    """Check if the job was posted within the last N days."""
    created = parse_created(created_str)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return created >= cutoff


async def fetch_jobs_from_adzuna(keyword: str, days_ago: int = 7) -> List[Dict]:
    """
    Fetch jobs from Adzuna API for UK/London, then:
    1. Filter by date range (days_ago) - done locally since API param is unreliable
    2. Filter by whitelist match or finance relevance
    3. Sort by whitelist priority then date
    """
    # Fetch multiple pages to get more results
    all_results = []
    for page in range(1, 4):  # First 3 pages = up to 150 results
        url = f"https://api.adzuna.com/v1/api/jobs/gb/search/{page}"
        params = {
            "app_id": APP_ID,
            "app_key": APP_KEY,
            "what": keyword,
            "where": "London",
            "results_per_page": 50,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    print(f"  -> ERROR fetching page {page}: {resp.status}")
                    break
                data = await resp.json()

        results = data.get("results", [])
        if not results:
            break

        all_results.extend(results)
        print(f"  -> Page {page}: {len(results)} results")

    if not all_results:
        print("  -> No results from API")
        return []

    print(f"  -> Total raw results: {len(all_results)}")

    # Date filter
    date_filtered = [
        job for job in all_results
        if is_within_days(job.get("created", ""), days_ago)
    ]
    print(f"  -> After date filter ({days_ago} days): {len(date_filtered)} results")

    jobs = []

    for job in date_filtered:
        company = (job.get("company", {}).get("display_name", "") or "").lower()
        title = (job.get("title", "") or "").lower()
        description = (job.get("description", "") or "").lower()
        location = job.get("location", {}).get("display_name", "UK")
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")
        salary_is_predicted = job.get("salary_is_predicted", False)
        created = job.get("created", "")
        redirect_url = job.get("redirect_url", "")
        category = job.get("category", {}).get("label", "")
        contract_type = job.get("contract_type", "permanent")

        # Whitelist match
        whitelist_match = any(w in company or w in title for w in FINANCE_WHITELIST)

        # Finance relevance via keywords
        finance_relevant = any(
            kw in company or kw in title or kw in description or kw in category.lower()
            for kw in FINANCE_KEYWORDS
        )

        # Keep whitelist matches + finance-relevant jobs
        if whitelist_match or finance_relevant:
            jobs.append({
                "id": job.get("id"),
                "title": job.get("title", ""),
                "company": job.get("company", {}).get("display_name", "Unknown"),
                "location": location,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "salary_predicted": salary_is_predicted,
                "created": created,
                "description": (job.get("description", "") or "")[:500],
                "url": redirect_url,
                "category": category,
                "whitelist_match": whitelist_match,
                "contract_type": contract_type,
            })

    # Sort: whitelist matches first, then newest first
    jobs.sort(key=lambda j: (not j["whitelist_match"], j["created"]), reverse=True)
    return jobs
