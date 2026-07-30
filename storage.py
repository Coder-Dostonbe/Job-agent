"""Ko'rilgan vakansiyalar tarixi — bir vakansiya ikki marta hisobotga tushmasin.

Ikki backend: `DATABASE_URL` berilgan bo'lsa PostgreSQL, aks holda lokal
SQLite fayli. GitHub Actions har run'da toza mashina beradi, ya'ni SQLite
fayli yo'qoladi va agent har kuni o'sha vakansiyalarni qaytadan yuboradi —
shuning uchun jadval bo'yicha ishlaganda Postgres kerak. Lokal testda esa
hech narsa sozlamasdan SQLite ishlayveradi.
"""
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import config

log = logging.getLogger("storage")

DDL = """
    CREATE TABLE IF NOT EXISTS vacancies (
        url TEXT PRIMARY KEY,
        source TEXT,
        title TEXT,
        score INTEGER,
        ai_score INTEGER,
        first_seen TEXT
    )
"""

# Postgres ishlamay qolsa SQLite'ga tushamiz: hisobot kelmay qolgandan ko'ra
# takroriy e'lonli hisobot yaxshiroq (va muammo darrov ko'zga tashlanadi).
_use_pg = bool(config.DATABASE_URL)


def _connect():
    global _use_pg
    if _use_pg:
        try:
            import psycopg
            return psycopg.connect(config.DATABASE_URL), "%s"
        except Exception as e:
            log.error("Postgres'ga ulanib bo'lmadi, SQLite'ga o'tildi: %s", e)
            _use_pg = False
    return sqlite3.connect(config.DB_PATH), "?"


@contextmanager
def _db():
    """Ochiq ulanish va shu drayverning parametr belgisi ('%s' yoki '?')."""
    conn, ph = _connect()
    try:
        cur = conn.cursor()  # psycopg'da executemany faqat kursorda bor
        cur.execute(DDL)
        conn.commit()
        yield cur, ph
        conn.commit()
    finally:
        conn.close()


def filter_new(vacancies: list[dict]) -> list[dict]:
    """Faqat oldin ko'rilmagan vakansiyalarni qaytaradi (run ichida ham dedup)."""
    with _db() as (cur, _):
        cur.execute("SELECT url FROM vacancies")
        seen = {row[0] for row in cur.fetchall()}
    unique, out = set(), []
    for v in vacancies:
        if v["url"] and v["url"] not in seen and v["url"] not in unique:
            unique.add(v["url"])
            out.append(v)
    return out


def save(vacancies: list[dict]) -> None:
    now = datetime.now().isoformat()
    rows = [
        (v["url"], v["source"], v["title"], v.get("score", 0),
         (v.get("ai") or {}).get("score", 0), now)
        for v in vacancies
    ]
    if not rows:
        return
    with _db() as (cur, ph):
        cur.executemany(
            f"INSERT INTO vacancies VALUES ({','.join([ph] * 6)}) "
            f"ON CONFLICT (url) DO NOTHING",
            rows,
        )


def skill_stats(vacancies: list[dict]) -> dict[str, int]:
    """Bugungi vakansiyalarda qaysi skill necha marta so'ralgani — CV maslahat uchun."""
    track = ["python", "django", "fastapi", "flask", "postgresql", "docker",
             "redis", "celery", "linux", "git", "rest", "javascript", "react",
             "kubernetes", "aws", "английск", "english"]
    counts = {}
    for v in vacancies:
        text = f"{v['title']} {v['text']}".lower()
        for s in track:
            if s in text:
                counts[s] = counts.get(s, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))
