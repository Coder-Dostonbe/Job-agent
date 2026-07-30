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


def source_group(v: dict) -> str:
    """Kvota uchun manba nomi. Telegram kanallari alohida emas, birga sanaladi
    ("t.me/UstozShogird", "t.me/python_jobs_uz" → "telegram")."""
    src = v.get("source", "")
    return "telegram" if src.startswith("t.me/") else src


def select(scored: list[dict]) -> list[dict]:
    """Hisobotga tushadigan vakansiyalarni tanlaydi.

    hh.uz kuniga ~90 ta e'lon beradi va tavsifi to'liq bo'lgani uchun ball
    bo'yicha ham yuqori chiqadi — oddiy "eng yuqori N ta" ro'yxatda OLX va
    Telegram umuman ko'rinmay qoladi. Shuning uchun avval har bir manbaga
    kvota beriladi; kvota to'lmay qolgan joylar esa qolgan eng yaxshi
    vakansiyalarga o'tadi. Umumiy chegara — REPORT_LIMIT.

    `scored` ball bo'yicha saralangan bo'lishi kutiladi.
    """
    quota, rest, used = [], [], {}
    for v in scored:
        g = source_group(v)
        if used.get(g, 0) < config.REPORT_SOURCE_QUOTA:
            used[g] = used.get(g, 0) + 1
            quota.append(v)
        else:
            rest.append(v)
    picked = quota[: config.REPORT_LIMIT]
    picked += rest[: config.REPORT_LIMIT - len(picked)]
    picked.sort(key=lambda v: -(v["ai"]["score"] if v.get("ai") else v["score"]))
    return picked


def build_report(shown: list[dict], stats: dict, total_new: int,
                 total_matched: int | None = None) -> str:
    """`shown` — ro'yxatga tushadiganlar (select natijasi),
    `total_matched` — umuman mos kelganlar soni (undan ko'pi ko'rsatilmaydi)."""
    matched = len(shown) if total_matched is None else total_matched
    header = f"Yangi vakansiyalar: {total_new} ta, mos kelganlari: {matched} ta"
    if matched > len(shown):
        header += f" (eng yaxshi {len(shown)} tasi)"
    lines = [f"📊 <b>Kunlik ish hisoboti</b>\n{header}\n"]

    for i, v in enumerate(shown, 1):
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
