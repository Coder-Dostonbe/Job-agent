"""Telegram ish kanallaridan postlarni o'qish (Telethon, user-akkaunt orqali).

GitHub Actions uchun: TG_SESSION_STRING env var orqali string session ishlatiladi.
Local uchun: 'agent.session' fayli ishlatiladi.
Session yaratish: python create_session.py
"""
import logging
import os
from datetime import datetime, timedelta, timezone

import config
import health

log = logging.getLogger("tg")

SOURCE = "telegram"  # `reporter.source_group` bilan bir xil nom
KEYWORDS = ["python", "django", "backend", "бэкенд", "бекенд"]


async def collect() -> list[dict]:
    health.expect(SOURCE)
    if not (config.TG_API_ID and config.TG_API_HASH):
        log.warning("TG_API_ID/TG_API_HASH yo'q — Telegram collector o'tkazib yuborildi")
        health.skipped(SOURCE, "TG_API_ID/TG_API_HASH sozlanmagan")
        return []

    # Session mavjudligini tekshir
    has_string_session = bool(getattr(config, 'TG_SESSION_STRING', ''))
    has_session_file = os.path.exists("agent.session")

    if not has_string_session and not has_session_file:
        log.warning(
            "Telethon session yo'q (agent.session ham, TG_SESSION_STRING ham). "
            "Telegram kanallar o'tkazib yuborildi."
        )
        health.skipped(
            SOURCE, "Telethon session yo'q (agent.session ham, TG_SESSION_STRING ham)"
        )
        return []

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    results = []
    since = datetime.now(timezone.utc) - timedelta(hours=config.TG_LOOKBACK_HOURS)

    if has_string_session:
        session = StringSession(config.TG_SESSION_STRING)
    else:
        session = "agent"

    scanned, silent = 0, []
    try:
        async with TelegramClient(
            session, int(config.TG_API_ID), config.TG_API_HASH
        ) as client:
            for channel in config.TG_CHANNELS:
                channel_posts = 0
                try:
                    async for msg in client.iter_messages(channel, limit=80):
                        if msg.date < since:
                            break
                        channel_posts += 1
                        text = (msg.text or "").strip()
                        low = text.lower()
                        if text and any(k in low for k in KEYWORDS):
                            results.append({
                                "source": f"t.me/{channel}",
                                "url": f"https://t.me/{channel}/{msg.id}",
                                "title": text.split("\n")[0][:90],
                                "company": "",
                                "salary": "",
                                "experience": "",
                                "text": text[:1500],
                                "published_at": msg.date.isoformat(),
                            })
                except Exception as e:
                    log.error("Kanal o'qishda xato (%s): %s", channel, e)
                    health.error(SOURCE, f"@{channel}: {e}")
                    continue
                scanned += channel_posts
                if not channel_posts:
                    silent.append(channel)
    except Exception as e:
        # Sessiya eskirgan / bekor qilingan, tarmoq yiqilgan va h.k.
        # Ilgari bu butun agentni yiqitardi — endi faqat shu manba yo'qoladi.
        log.error("Telegram'ga ulanib bo'lmadi: %s", e)
        health.error(SOURCE, f"ulanib bo'lmadi: {e}")
        return results

    if silent:
        # Kanal o'qildi, lekin oxirgi TG_LOOKBACK_HOURS soatda bironta post yo'q.
        # Bir-ikkitasi normal; hammasi jim bo'lsa — sessiya yoki kanallar bilan
        # muammo bor (qarang HOLAT.md: `python_jobs_uz` bir yil jim edi).
        log.info("Postsiz kanallar (%d/%d): %s",
                 len(silent), len(config.TG_CHANNELS), ", ".join(silent))
        if len(silent) == len(config.TG_CHANNELS):
            health.error(SOURCE, f"barcha {len(silent)} kanal {config.TG_LOOKBACK_HOURS} "
                                 f"soatda 0 ta post berdi")

    log.info("Telegram: %d ta postdan %d tasi mos", scanned, len(results))
    health.found(SOURCE, len(results), scanned=scanned)
    return results
