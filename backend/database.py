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
