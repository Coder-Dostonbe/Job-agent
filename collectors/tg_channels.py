"""Telegram ish kanallaridan postlarni o'qish (ochiq t.me/s/ ko'rinishi).

Login, sessiya yoki API kalit kerak emas — har bir to'liq ochiq (public)
kanalning web-preview sahifasi (`https://t.me/s/<username>`) orqali o'qiladi.
Yangi kanal qo'shishdan oldin tekshiring: shu manzil ochilishi va oxirgi
posti yaqin kunlarda bo'lishi kerak.
"""
import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

import config
import health

log = logging.getLogger("tg")

SOURCE = "telegram"  # `reporter.source_group` bilan bir xil nom
KEYWORDS = ["python", "django", "backend", "бэкенд", "бекенд"]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-agent/1.0)"}
MAX_PAGES = 5  # kanal juda faol bo'lsa ham cheksiz orqaga tushib ketmasin


def _parse_page(html: str) -> list[dict]:
    """Bitta `t.me/s/...` sahifasidagi postlarni ajratib oladi."""
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for wrap in soup.select(".tgme_widget_message_wrap"):
        post_div = wrap.select_one("[data-post]")
        time_el = wrap.select_one("time")
        if not post_div or not time_el or not time_el.get("datetime"):
            continue
        text_el = wrap.select_one(".tgme_widget_message_text")
        posts.append({
            "post_id": post_div["data-post"],  # "kanal/12345"
            "published": datetime.fromisoformat(time_el["datetime"]),
            "text": text_el.get_text("\n").strip() if text_el else "",
        })
    return posts


def _fetch_channel(channel: str, since: datetime) -> list[dict]:
    """Kanalni o'qiydi; eng eski post `since`dan oldin bo'lguncha orqaga
    sahifalaydi (bitta sahifa — so'nggi ~20 post)."""
    all_posts: list[dict] = []
    before = None
    for _ in range(MAX_PAGES):
        url = f"https://t.me/s/{channel}"
        if before:
            url += f"?before={before}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        posts = _parse_page(resp.text)
        if not posts:
            break
        all_posts.extend(posts)
        oldest = min(posts, key=lambda p: p["published"])
        if oldest["published"] < since:
            break
        before = oldest["post_id"].rsplit("/", 1)[-1]
    return all_posts


def collect() -> list[dict]:
    health.expect(SOURCE)
    if not config.TG_CHANNELS:
        log.warning("TG_CHANNELS bo'sh — Telegram kanallar o'tkazib yuborildi")
        health.skipped(SOURCE, "TG_CHANNELS sozlanmagan")
        return []

    since = datetime.now(timezone.utc) - timedelta(hours=config.TG_LOOKBACK_HOURS)
    results = []
    scanned, silent = 0, []

    for channel in config.TG_CHANNELS:
        try:
            posts = _fetch_channel(channel, since)
        except Exception as e:
            log.error("Kanal o'qishda xato (%s): %s", channel, e)
            health.error(SOURCE, f"@{channel}: {e}")
            continue

        channel_posts = 0
        for p in posts:
            if p["published"] < since:
                continue
            channel_posts += 1
            text = p["text"]
            low = text.lower()
            if text and any(k in low for k in KEYWORDS):
                chan, msg_id = p["post_id"].split("/", 1)
                results.append({
                    "source": f"t.me/{chan}",
                    "url": f"https://t.me/{chan}/{msg_id}",
                    "title": text.split("\n")[0][:90],
                    "company": "",
                    "salary": "",
                    "experience": "",
                    "text": text[:1500],
                    "published_at": p["published"].isoformat(),
                })
        scanned += channel_posts
        if not channel_posts:
            silent.append(channel)

    if silent:
        # Kanal o'qildi, lekin oxirgi TG_LOOKBACK_HOURS soatda bironta post yo'q.
        # Bir-ikkitasi normal; hammasi jim bo'lsa — kanal ro'yxati bilan muammo bor.
        log.info("Postsiz kanallar (%d/%d): %s",
                 len(silent), len(config.TG_CHANNELS), ", ".join(silent))
        if len(silent) == len(config.TG_CHANNELS):
            health.error(SOURCE, f"barcha {len(silent)} kanal {config.TG_LOOKBACK_HOURS} "
                                 f"soatda 0 ta post berdi")

    log.info("Telegram: %d ta postdan %d tasi mos", scanned, len(results))
    health.found(SOURCE, len(results), scanned=scanned)
    return results
