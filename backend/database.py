import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "jobs_cache.db"))

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS job_cache (
                cache_key TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
        ''')
        await db.commit()

async def get_cached(cache_key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT content, fetched_at FROM job_cache WHERE cache_key = ?",
            (cache_key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"content": row[0], "fetched_at": row[1]}
    return None

async def save_cache(cache_key: str, content: str):
    from datetime import datetime
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO job_cache (cache_key, content, fetched_at) VALUES (?, ?, ?)",
            (cache_key, content, datetime.utcnow().isoformat())
        )
        await db.commit()

# --- Subscriber table ---

async def init_subscribers_table():
    async with aiosqlite.connect(DB_PATH) as db:
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

async def create_subscriber(email: str, name: str, keywords: str, location: str, days_ago: int, min_salary: int = None):
    from datetime import datetime
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO subscribers (email, name, keywords, location, days_ago, min_salary, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (email, name, keywords, location, days_ago, min_salary, datetime.utcnow().isoformat())
            )
            await db.commit()
            return True
        except Exception:
            return False

async def get_active_subscribers(tier: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        query = "SELECT id, email, name, keywords, location, days_ago, min_salary, tier FROM subscribers WHERE active = 1"
        params = []
        if tier:
            query += " AND tier = ?"
            params.append(tier)
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0], "email": r[1], "name": r[2],
                    "keywords": r[3], "location": r[4],
                    "days_ago": r[5], "min_salary": r[6],
                    "tier": r[7]
                }
                for r in rows
            ]

async def update_subscriber_alert_count(subscriber_id: int):
    from datetime import datetime
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE subscribers SET alert_count = alert_count + 1, last_alert_at = ? WHERE id = ?""",
            (datetime.utcnow().isoformat(), subscriber_id)
        )
        await db.commit()

async def get_subscriber_by_email(email: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, email, name, keywords, location, days_ago, min_salary, tier, active FROM subscribers WHERE email = ?",
            (email,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0], "email": row[1], "name": row[2],
                    "keywords": row[3], "location": row[4],
                    "days_ago": row[5], "min_salary": row[6],
                    "tier": row[7], "active": row[8]
                }
    return None

async def delete_subscriber(email: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscribers WHERE email = ?", (email,))
        await db.commit()

async def update_subscriber_tier(email: str, tier: str, stripe_customer_id: str = None, stripe_subscription_id: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if stripe_customer_id:
            await db.execute(
                "UPDATE subscribers SET tier = ?, stripe_customer_id = ?, stripe_subscription_id = ? WHERE email = ?",
                (tier, stripe_customer_id, stripe_subscription_id, email)
            )
        else:
            await db.execute(
                "UPDATE subscribers SET tier = ? WHERE email = ?",
                (tier, email)
            )
        await db.commit()

async def update_subscriber_keywords(email: str, keywords: str, location: str, days_ago: int, min_salary: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscribers SET keywords = ?, location = ?, days_ago = ?, min_salary = ? WHERE email = ?",
            (keywords, location, days_ago, min_salary, email)
        )
        await db.commit()

# --- Sent alerts table (deduplication) ---

async def init_sent_alerts_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sent_alerts (
                subscriber_id INTEGER,
                job_id TEXT,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (subscriber_id, job_id)
            )
        ''')
        await db.commit()

async def is_alert_sent(subscriber_id: int, job_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM sent_alerts WHERE subscriber_id = ? AND job_id = ?",
            (subscriber_id, job_id)
        ) as cursor:
            return await cursor.fetchone() is not None

async def mark_alert_sent(subscriber_id: int, job_id: str):
    from datetime import datetime
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sent_alerts (subscriber_id, job_id, sent_at) VALUES (?, ?, ?)",
            (subscriber_id, job_id, datetime.utcnow().isoformat())
        )
        await db.commit()

async def prune_old_sent_alerts(days: int = 30):
    """Remove sent alert records older than N days to keep DB small."""
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sent_alerts WHERE sent_at < ?", (cutoff,))
        await db.commit()

# --- Rate limiting table ---

async def init_rate_limits_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS rate_limits (
                client_ip TEXT PRIMARY KEY,
                request_count INTEGER NOT NULL DEFAULT 0,
                window_start TEXT NOT NULL
            )
        ''')
        await db.commit()

async def check_rate_limit_db(client_ip: str, max_requests: int = 10, window_seconds: int = 60) -> bool:
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=window_seconds)

    async with aiosqlite.connect(DB_PATH) as db:
        # Clean old entries
        await db.execute(
            "DELETE FROM rate_limits WHERE window_start < ?",
            (window_start.isoformat(),)
        )
        await db.commit()

        # Check current count
        async with db.execute(
            "SELECT request_count FROM rate_limits WHERE client_ip = ?",
            (client_ip,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                if row[0] >= max_requests:
                    return False
                await db.execute(
                    "UPDATE rate_limits SET request_count = request_count + 1 WHERE client_ip = ?",
                    (client_ip,)
                )
                await db.commit()
                return True
            else:
                await db.execute(
                    "INSERT INTO rate_limits (client_ip, request_count, window_start) VALUES (?, 1, ?)",
                    (client_ip, now.isoformat())
                )
                await db.commit()
                return True
