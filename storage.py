"""Ko'rilgan vakansiyalar tarixi — bir vakansiya ikki marta hisobotga tushmasin.

Ikki backend: `DATABASE_URL` berilgan bo'lsa PostgreSQL, aks holda lokal
SQLite fayli. GitHub Actions har run'da toza mashina beradi, ya'ni SQLite
fayli yo'qoladi va agent har kuni o'sha vakansiyalarni qaytadan yuboradi —
shuning uchun jadval bo'yicha ishlaganda Postgres kerak. Lokal testda esa
hech narsa sozlamasdan SQLite ishlayveradi.
"""
import logging
import re
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


def _title_key(source: str, title: str) -> str:
    """Sarlavha dedupi uchun kalit. Tinish belgilari, emoji va ortiqcha
    bo'shliqlar tashlanadi: "Python dasturchi!!!" == "python  dasturchi"."""
    norm = re.sub(r"[^\w]+", " ", (title or "").lower(), flags=re.UNICODE).strip()
    return f"{source}|{norm}" if norm else ""


def filter_new(vacancies: list[dict]) -> list[dict]:
    """Faqat oldin ko'rilmagan vakansiyalarni qaytaradi (run ichida ham dedup).

    Asosiy kalit — URL. `config.TITLE_DEDUP_SOURCES` dagi manbalar uchun
    qo'shimcha ravishda sarlavha ham tekshiriladi: OLX'da bir e'lon qayta
    joylanganda URL yangi bo'ladi, ya'ni URL dedupi uni ushlamaydi.
    """
    with _db() as (cur, _):
        cur.execute("SELECT url, source, title FROM vacancies")
        rows = cur.fetchall()
    seen_urls = {r[0] for r in rows}
    seen_titles = {
        _title_key(r[1], r[2]) for r in rows
        if r[1] in config.TITLE_DEDUP_SOURCES
    } - {""}

    new_urls, new_titles, out = set(), set(), []
    for v in vacancies:
        if not v["url"] or v["url"] in seen_urls or v["url"] in new_urls:
            continue
        if v["source"] in config.TITLE_DEDUP_SOURCES:
            key = _title_key(v["source"], v["title"])
            if key and (key in seen_titles or key in new_titles):
                log.info("Takror (sarlavha bo'yicha): %s", v["title"][:60])
                continue
            new_titles.add(key)
        new_urls.add(v["url"])
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
