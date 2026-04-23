import os
import aiosqlite
import re
from contextlib import asynccontextmanager

try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "jobs_cache.db"))
USE_PG = bool(DATABASE_URL and HAS_ASYNCPG)


def _to_pg_params(sql: str) -> str:
    """Convert SQLite ? placeholders to Postgres $1, $2, etc."""
    counter = [0]
    def replacer(m):
        counter[0] += 1
        return f"${counter[0]}"
    return re.sub(r'\?', replacer, sql)


class DBConnection:
    """Unified connection wrapper for SQLite and Postgres."""
    def __init__(self, conn):
        self.conn = conn
        self.is_pg = USE_PG

    async def execute(self, sql: str, *args):
        if self.is_pg:
            await self.conn.execute(_to_pg_params(sql), *args)
        else:
            await self.conn.execute(sql, args)

    async def fetchone(self, sql: str, *args):
        if self.is_pg:
            return await self.conn.fetchrow(_to_pg_params(sql), *args)
        else:
            async with self.conn.execute(sql, args) as cursor:
                return await cursor.fetchone()

    async def fetchall(self, sql: str, *args):
        if self.is_pg:
            return await self.conn.fetch(_to_pg_params(sql), *args)
        else:
            async with self.conn.execute(sql, args) as cursor:
                return await cursor.fetchall()

    async def commit(self):
        if not self.is_pg:
            await self.conn.commit()

    async def close(self):
        await self.conn.close()


@asynccontextmanager
async def get_db():
    if USE_PG:
        conn = await asyncpg.connect(DATABASE_URL)
    else:
        conn = await aiosqlite.connect(DB_PATH)
    db = DBConnection(conn)
    try:
        yield db
    finally:
        await db.close()


# ─── Table creation ───

async def init_db():
    async with get_db() as db:
        if db.is_pg:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS job_cache (
                    cache_key TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                )
            ''')
        else:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS job_cache (
                    cache_key TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                )
            ''')
        await db.commit()


async def init_subscribers_table():
    async with get_db() as db:
        if db.is_pg:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS subscribers (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    keywords TEXT NOT NULL DEFAULT '[]',
                    location TEXT NOT NULL DEFAULT 'London',
                    days_ago INTEGER NOT NULL DEFAULT 7,
                    min_salary INTEGER,
                    tier TEXT NOT NULL DEFAULT 'free',
                    stripe_customer_id TEXT,
                    stripe_subscription_id TEXT,
                    created_at TEXT NOT NULL,
                    alert_count INTEGER NOT NULL DEFAULT 0,
                    last_alert_at TEXT,
                    active INTEGER NOT NULL DEFAULT 1
                )
            ''')
        else:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS subscribers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    keywords TEXT NOT NULL DEFAULT '[]',
                    location TEXT NOT NULL DEFAULT 'London',
                    days_ago INTEGER NOT NULL DEFAULT 7,
                    min_salary INTEGER,
                    tier TEXT NOT NULL DEFAULT 'free',
                    stripe_customer_id TEXT,
                    stripe_subscription_id TEXT,
                    created_at TEXT NOT NULL,
                    alert_count INTEGER NOT NULL DEFAULT 0,
                    last_alert_at TEXT,
                    active INTEGER NOT NULL DEFAULT 1
                )
            ''')
        await db.commit()


async def init_sent_alerts_table():
    async with get_db() as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sent_alerts (
                subscriber_id INTEGER,
                job_id TEXT,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (subscriber_id, job_id)
            )
        ''')
        await db.commit()


async def init_rate_limits_table():
    async with get_db() as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS rate_limits (
                client_ip TEXT PRIMARY KEY,
                request_count INTEGER NOT NULL DEFAULT 0,
                window_start TEXT NOT NULL
            )
        ''')
        await db.commit()


async def init_jobs_table():
    async with get_db() as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                salary_min REAL,
                salary_max REAL,
                salary_predicted INTEGER DEFAULT 0,
                created TEXT NOT NULL,
                description TEXT,
                url TEXT NOT NULL,
                category TEXT,
                whitelist_match INTEGER DEFAULT 0,
                contract_type TEXT,
                fetched_at TEXT NOT NULL
            )
        ''')
        await db.commit()


# ─── Cache operations ───

async def get_cached(cache_key: str):
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT content, fetched_at FROM job_cache WHERE cache_key = ?",
            cache_key
        )
        if row:
            return {"content": row[0], "fetched_at": row[1]}
    return None


async def save_cache(cache_key: str, content: str):
    from datetime import datetime
    async with get_db() as db:
        if db.is_pg:
            await db.execute(
                '''INSERT INTO job_cache (cache_key, content, fetched_at)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (cache_key)
                   DO UPDATE SET content = EXCLUDED.content, fetched_at = EXCLUDED.fetched_at''',
                cache_key, content, datetime.utcnow().isoformat()
            )
        else:
            await db.execute(
                "INSERT OR REPLACE INTO job_cache (cache_key, content, fetched_at) VALUES (?, ?, ?)",
                cache_key, content, datetime.utcnow().isoformat()
            )
        await db.commit()


async def get_all_cache():
    async with get_db() as db:
        return await db.fetchall("SELECT cache_key, fetched_at FROM job_cache")


# ─── Subscriber operations ───

async def create_subscriber(email: str, name: str, keywords: str, location: str, days_ago: int, min_salary: int = None):
    from datetime import datetime
    async with get_db() as db:
        try:
            await db.execute(
                """INSERT INTO subscribers (email, name, keywords, location, days_ago, min_salary, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                email, name, keywords, location, days_ago, min_salary, datetime.utcnow().isoformat()
            )
            await db.commit()
            return True
        except Exception:
            return False


async def get_active_subscribers(tier: str = None):
    async with get_db() as db:
        base = "SELECT id, email, name, keywords, location, days_ago, min_salary, tier FROM subscribers WHERE active = 1"
        if tier:
            rows = await db.fetchall(base + " AND tier = ?", tier)
        else:
            rows = await db.fetchall(base)
        return [
            {"id": r[0], "email": r[1], "name": r[2],
             "keywords": r[3], "location": r[4],
             "days_ago": r[5], "min_salary": r[6],
             "tier": r[7]}
            for r in rows
        ]


async def update_subscriber_alert_count(subscriber_id: int):
    from datetime import datetime
    async with get_db() as db:
        await db.execute(
            """UPDATE subscribers SET alert_count = alert_count + 1, last_alert_at = ? WHERE id = ?""",
            datetime.utcnow().isoformat(), subscriber_id
        )
        await db.commit()


async def get_subscriber_by_email(email: str):
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT id, email, name, keywords, location, days_ago, min_salary, tier, active FROM subscribers WHERE email = ?",
            email
        )
        if row:
            return {
                "id": row[0], "email": row[1], "name": row[2],
                "keywords": row[3], "location": row[4],
                "days_ago": row[5], "min_salary": row[6],
                "tier": row[7], "active": row[8]
            }
    return None


async def delete_subscriber(email: str):
    async with get_db() as db:
        await db.execute("DELETE FROM subscribers WHERE email = ?", email)
        await db.commit()


async def update_subscriber_tier(email: str, tier: str, stripe_customer_id: str = None, stripe_subscription_id: str = None):
    async with get_db() as db:
        if stripe_customer_id:
            await db.execute(
                "UPDATE subscribers SET tier = ?, stripe_customer_id = ?, stripe_subscription_id = ? WHERE email = ?",
                tier, stripe_customer_id, stripe_subscription_id, email
            )
        else:
            await db.execute(
                "UPDATE subscribers SET tier = ? WHERE email = ?",
                tier, email
            )
        await db.commit()


async def update_subscriber_keywords(email: str, keywords: str, location: str, days_ago: int, min_salary: int = None):
    async with get_db() as db:
        await db.execute(
            "UPDATE subscribers SET keywords = ?, location = ?, days_ago = ?, min_salary = ? WHERE email = ?",
            keywords, location, days_ago, min_salary, email
        )
        await db.commit()


# ─── Sent alerts (deduplication) ───

async def is_alert_sent(subscriber_id: int, job_id: str) -> bool:
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT 1 FROM sent_alerts WHERE subscriber_id = ? AND job_id = ?",
            subscriber_id, job_id
        )
        return row is not None


async def mark_alert_sent(subscriber_id: int, job_id: str):
    from datetime import datetime
    async with get_db() as db:
        if db.is_pg:
            await db.execute(
                '''INSERT INTO sent_alerts (subscriber_id, job_id, sent_at)
                   VALUES ($1, $2, $3)
                   ON CONFLICT DO NOTHING''',
                subscriber_id, job_id, datetime.utcnow().isoformat()
            )
        else:
            await db.execute(
                "INSERT OR IGNORE INTO sent_alerts (subscriber_id, job_id, sent_at) VALUES (?, ?, ?)",
                subscriber_id, job_id, datetime.utcnow().isoformat()
            )
        await db.commit()


async def prune_old_sent_alerts(days: int = 30):
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with get_db() as db:
        await db.execute("DELETE FROM sent_alerts WHERE sent_at < ?", cutoff)
        await db.commit()


# ─── Rate limiting ───

async def check_rate_limit_db(client_ip: str, max_requests: int = 10, window_seconds: int = 60) -> bool:
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=window_seconds)

    async with get_db() as db:
        await db.execute(
            "DELETE FROM rate_limits WHERE window_start < ?",
            window_start.isoformat()
        )
        await db.commit()

        row = await db.fetchone(
            "SELECT request_count FROM rate_limits WHERE client_ip = ?",
            client_ip
        )
        if row:
            if row[0] >= max_requests:
                return False
            await db.execute(
                "UPDATE rate_limits SET request_count = request_count + 1 WHERE client_ip = ?",
                client_ip
            )
            await db.commit()
            return True
        else:
            await db.execute(
                "INSERT INTO rate_limits (client_ip, request_count, window_start) VALUES (?, 1, ?)",
                client_ip, now.isoformat()
            )
            await db.commit()
            return True


# ─── Job detail storage ───

async def upsert_job(job: dict):
    from datetime import datetime
    async with get_db() as db:
        if db.is_pg:
            await db.execute(
                '''INSERT INTO jobs (id, title, company, location, salary_min, salary_max, salary_predicted,
                                    created, description, url, category, whitelist_match, contract_type, fetched_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                   ON CONFLICT (id)
                   DO UPDATE SET title = EXCLUDED.title, company = EXCLUDED.company,
                                 location = EXCLUDED.location, salary_min = EXCLUDED.salary_min,
                                 salary_max = EXCLUDED.salary_max, salary_predicted = EXCLUDED.salary_predicted,
                                 created = EXCLUDED.created, description = EXCLUDED.description,
                                 url = EXCLUDED.url, category = EXCLUDED.category,
                                 whitelist_match = EXCLUDED.whitelist_match, contract_type = EXCLUDED.contract_type,
                                 fetched_at = EXCLUDED.fetched_at''',
                job.get("id"), job.get("title", ""), job.get("company", "Unknown"),
                job.get("location", "UK"), job.get("salary_min"), job.get("salary_max"),
                1 if job.get("salary_predicted") else 0,
                job.get("created", ""), job.get("description", ""), job.get("url", ""),
                job.get("category", ""), 1 if job.get("whitelist_match") else 0,
                job.get("contract_type", "permanent"), datetime.utcnow().isoformat()
            )
        else:
            await db.execute(
                '''INSERT OR REPLACE INTO jobs (id, title, company, location, salary_min, salary_max, salary_predicted,
                                                created, description, url, category, whitelist_match, contract_type, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                job.get("id"), job.get("title", ""), job.get("company", "Unknown"),
                job.get("location", "UK"), job.get("salary_min"), job.get("salary_max"),
                1 if job.get("salary_predicted") else 0,
                job.get("created", ""), job.get("description", ""), job.get("url", ""),
                job.get("category", ""), 1 if job.get("whitelist_match") else 0,
                job.get("contract_type", "permanent"), datetime.utcnow().isoformat()
            )
        await db.commit()


async def get_job_by_id(job_id: str):
    async with get_db() as db:
        row = await db.fetchone(
            """SELECT id, title, company, location, salary_min, salary_max, salary_predicted,
                      created, description, url, category, whitelist_match, contract_type
               FROM jobs WHERE id = ?""",
            job_id
        )
        if not row:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "company": row[2],
            "location": row[3],
            "salary_min": row[4],
            "salary_max": row[5],
            "salary_predicted": bool(row[6]),
            "created": row[7],
            "description": row[8],
            "url": row[9],
            "category": row[10],
            "whitelist_match": bool(row[11]),
            "contract_type": row[12],
        }
