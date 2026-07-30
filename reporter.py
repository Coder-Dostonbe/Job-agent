"""Kunlik hisobotni Telegram botga yuborish."""
import logging
from html import escape

import requests

import config

log = logging.getLogger("reporter")

VERDICT_EMOJI = {
    "topshirish_kerak": "🟢",
    "urinib_korish": "🟡",
    "vaqt_sarflamaslik": "🔴",
}


def build_report(scored: list[dict], stats: dict, total_new: int) -> str:
    lines = [f"📊 <b>Kunlik ish hisoboti</b>\n"
             f"Yangi vakansiyalar: {total_new} ta, mos kelganlari: {len(scored)} ta\n"]

    for i, v in enumerate(scored[:10], 1):
        ai = v.get("ai")
        emoji = VERDICT_EMOJI.get(ai["verdict"], "⚪") if ai else "⚪"
        lines.append(f"{emoji} <b>{i}. {escape(v['title'][:70])}</b>")
        meta = " | ".join(filter(None, [v["source"], v["company"], v["salary"]]))
        if meta:
            lines.append(f"   {escape(meta)}")
        if ai:
            lines.append(f"   AI: {ai['score']}/100 — {escape(ai['reason'])}")
            lines.append(f"   💡 CV: {escape(ai['cv_tip'])}")
        else:
            lines.append(f"   Keyword ball: {v['score']}/100")
        # Uzun havola o'rniga bosiladigan matn
        lines.append(f'   <a href="{escape(v["url"], quote=True)}">🔗 Vakansiyani ko\'rish</a>\n')

    if stats:
        top = ", ".join(f"{k} ({n})" for k, n in list(stats.items())[:8])
        lines.append(f"📈 <b>Bugun eng ko'p so'ralgan skillar:</b> {top}")

    return "\n".join(lines)


def _split(text: str, limit: int = 3900) -> list[str]:
    """Telegram limiti 4096 belgi. Qatorlar bo'yicha bo'lamiz — HTML tegi
    (masalan <a href=...>) o'rtasidan kesilib qolmasligi uchun."""
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit and current:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


def send(text: str) -> None:
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        log.warning("Bot token/chat_id yo'q — hisobot konsolga chiqarildi:\n%s", text)
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    for chunk in _split(text):
        try:
            resp = requests.post(url, json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }, timeout=15)
            if not resp.ok:
                log.error("Telegram rad etdi (%s): %s", resp.status_code, resp.text[:200])
        except Exception as e:
            log.error("Telegram yuborishda xato: %s", e)
