"""Ko'rilgan vakansiyalar tarixi — bir vakansiya ikki marta hisobotga tushmasin.

Ikki backend: `DATABASE_URL` berilgan bo'lsa PostgreSQL, aks holda lokal
SQLite fayli. GitHub Actions har run'da toza mashina beradi, ya'ni SQLite
fayli yo'qoladi va agent har kuni o'sha vakansiyalarni qaytadan yuboradi —
shuning uchun jadval bo'yicha ishlaganda Postgres kerak. Lokal testda esa
hech narsa sozlamasdan SQLite ishlayveradi.

Backend'ning qaysi biri ishlayotgani har hisobotda ko'rinadi (`health.py`).
Postgres yiqilib SQLite'ga tushish — nosozlik, jimgina "yechim" emas: Actions
sharoitida u tarixni butunlay yo'q qiladi va agent har kuni o'sha
vakansiyalarni qaytadan yuborishni boshlaydi.
"""
import logging
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime

import config
import health

log = logging.getLogger("storage")

SOURCE = "storage"

DDL = (
    """
    CREATE TABLE IF NOT EXISTS vacancies (
        url TEXT PRIMARY KEY,
        source TEXT,
        title TEXT,
        score INTEGER,
        ai_score INTEGER,
        first_seen TEXT
    )
    """,
    # Har run'da har manba nechta e'lon qaytargani. Kundalik ishga kerak emas —
    # faqat keskin pasayishni sezish uchun (qarang: trend.py). Kuniga ~4 qator.
    """
    CREATE TABLE IF NOT EXISTS source_runs (
        source TEXT,
        ts TEXT,
        scanned INTEGER
    )
    """,
)

# Postgres ishlamay qolsa SQLite'ga tushamiz: hisobot kelmay qolgandan ko'ra
# takroriy e'lonli hisobot yaxshiroq. Lekin bu tushish **ko'rinishi** shart —
# ilgari u faqat logga yozilardi, ya'ni Actions logini ochib ko'rmaguningizcha
# bilinmasdi. Natijada tarix bir necha kun yo'qolib turishi mumkin edi.
_use_pg = bool(config.DATABASE_URL)

# Bir xil ogohlantirish har ulanishda takrorlanmasin (run'da _db() bir necha
# marta ochiladi)
_reported: set[str] = set()


def reset_state() -> None:
    """Modul holatini tiklaydi — testlar va bitta jarayonda takroriy run uchun."""
    global _use_pg
    _use_pg = bool(config.DATABASE_URL)
    _reported.clear()


def _report_once(key: str, message: str) -> None:
    if key in _reported:
        return
    _reported.add(key)
    log.error("%s", message)
    # Xato bo'lsa ham ombor "ishga tushgan" komponent — aks holda hisobotda
    # kollektorlar uchun yozilgan "0 ta e'lon qaytardi" matni chiqib qoladi.
    health.alive(SOURCE)
    health.error(SOURCE, message)


def _on_actions() -> bool:
    """GitHub Actions'dami? U yerda disk har run tugashi bilan o'chadi, ya'ni
    SQLite zaxirasi umuman zaxira emas — bir martalik xotira."""
    return bool(os.getenv("GITHUB_ACTIONS"))


def _connect_pg():
    """Postgres ulanishi; vaqtinchalik uzilishda qayta uriniladi.

    Serverless baza sovuq holatdan uyg'onishi bir necha soniya olishi mumkin.
    Bitta timeout uchun butun tarixdan voz kechish — juda qimmat almashuv.
    """
    import psycopg

    last: Exception | None = None
    for attempt in range(1, config.DB_CONNECT_RETRIES + 1):
        try:
            return psycopg.connect(
                config.DATABASE_URL, connect_timeout=config.DB_CONNECT_TIMEOUT
            )
        except Exception as e:
            last = e
            log.warning(
                "Postgres urinish %d/%d muvaffaqiyatsiz: %s",
                attempt, config.DB_CONNECT_RETRIES, e,
            )
            if attempt < config.DB_CONNECT_RETRIES:
                time.sleep(config.DB_RETRY_DELAY * attempt)
    raise last  # type: ignore[misc]


def _fallback_message(op: str, exc: Exception) -> str:
    """Postgres yiqilganda hisobotga chiqadigan matn — oqibati bilan birga."""
    consequence = (
        "bugungi vakansiyalar tarixga yozilmadi, ertaga qayta yuboriladi"
        if op == "write"
        else "tarix o'qilmadi, ko'rilgan e'lonlar takror kelishi mumkin"
    )
    where = " (Actions'da SQLite fayli run tugashi bilan o'chadi)" if _on_actions() else ""
    return (
        f"Postgres ishlamadi, SQLite'ga o'tildi{where} — {consequence}. "
        f"Sabab: {type(exc).__name__}: {exc}"
    )


def _check_missing_url() -> None:
    """DATABASE_URL yo'qligi lokalda normal, Actions'da esa jimgina nosozlik:
    tarix hech qachon saqlanmaydi va har kuni o'sha e'lonlar keladi."""
    if config.DATABASE_URL or not _on_actions():
        return
    _report_once(
        "no-url",
        "DATABASE_URL sozlanmagan — Actions diski har run'dan keyin o'chadi, "
        "ya'ni tarix umuman saqlanmayapti va har kuni o'sha vakansiyalar qayta "
        "yuboriladi. Repo Secrets'iga DATABASE_URL qo'shing.",
    )


def _connect(op: str):
    global _use_pg
    if _use_pg:
        try:
            conn = _connect_pg()
            health.alive(SOURCE, "postgres")
            return conn, "%s"
        except Exception as e:
            _use_pg = False  # shu run'da qayta urinmaymiz — vaqtni yemasin
            _report_once("fallback", _fallback_message(op, e))
    else:
        _check_missing_url()
    health.alive(SOURCE, "sqlite (zaxira)" if config.DATABASE_URL else "sqlite")
    return sqlite3.connect(config.DB_PATH), "?"


@contextmanager
def _db(op: str = "read"):
    """Ochiq ulanish va shu drayverning parametr belgisi ('%s' yoki '?').

    `op` — faqat diagnostika uchun: o'qishda yiqilish takroriy e'lonlarga,
    yozishda yiqilish esa tarix yo'qolishiga olib keladi, xabari ham har xil.
    """
    conn, ph = _connect(op)
    try:
        cur = conn.cursor()  # psycopg'da executemany faqat kursorda bor
        for statement in DDL:
            cur.execute(statement)
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
    with _db("read") as (cur, _):
        cur.execute("SELECT url, source, title FROM vacancies")
        rows = cur.fetchall()
    log.info("Tarixda %d ta yozuv", len(rows))
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
    try:
        with _db("write") as (cur, ph):
            cur.executemany(
                f"INSERT INTO vacancies VALUES ({','.join([ph] * 6)}) "
                f"ON CONFLICT (url) DO NOTHING",
                rows,
            )
    except Exception as e:
        # Saqlash yiqilsa ham hisobot ketaversin: tayyor vakansiyalarni
        # yo'qotgandan ko'ra ertaga takrorlangani afzal. Ogohlantirish
        # hisobotning o'zida ko'rinadi.
        _report_once(
            "save-failed",
            f"{len(rows)} ta vakansiya tarixga yozilmadi — ertaga qayta "
            f"yuboriladi. Sabab: {type(e).__name__}: {e}",
        )


def record_counts(counts: dict[str, int]) -> None:
    """Bugungi run'da har manba nechta e'lon qaytarganini tarixga yozadi.

    Bu yozuvlarsiz keskin pasayishni sezib bo'lmaydi: taqqoslash uchun
    "odatda qancha bo'ladi" degan chiziq kerak, uni esa faqat o'tgan
    run'lardan olish mumkin (qarang: trend.py).
    """
    if not counts:
        return
    now = datetime.now().isoformat()
    rows = [(source, now, int(n)) for source, n in counts.items()]
    try:
        with _db("write") as (cur, ph):
            cur.executemany(
                f"INSERT INTO source_runs VALUES ({ph},{ph},{ph})", rows
            )
    except Exception as e:
        # Hisobotga ogohlantirish qo'shmaymiz: ombor yiqilgan bo'lsa,
        # bu haqda `_report_once` allaqachon gapirgan. Bu yerda takrorlash
        # foydalanuvchiga bir nosozlik uchun ikkinchi qatorni ko'rsatardi.
        log.warning("Trend uchun sonlar yozilmadi: %s: %s", type(e).__name__, e)


def recent_counts(limit: int) -> dict[str, list[int]]:
    """Oxirgi `limit` ta run'dagi sonlar, manba bo'yicha (eng yangisi birinchi).

    Tarix yo'q bo'lsa (birinchi run, yoki Postgres o'rniga bir martalik
    SQLite) bo'sh lug'at qaytadi — bu holda taqqoslash o'tkazib yuboriladi.
    """
    try:
        with _db("read") as (cur, _):
            cur.execute("SELECT source, scanned FROM source_runs ORDER BY ts DESC")
            rows = cur.fetchall()
    except Exception as e:
        log.warning("Trend tarixi o'qilmadi: %s: %s", type(e).__name__, e)
        return {}
    out: dict[str, list[int]] = {}
    for source, scanned in rows:
        bucket = out.setdefault(source, [])
        if len(bucket) < limit:
            bucket.append(int(scanned))
    return out


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
