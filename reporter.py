"""Kunlik hisobotni Telegram botga yuborish."""
import logging
import os
import traceback
from html import escape

import requests

import config
import health

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


def rank(v: dict) -> int:
    """Saralash bali: AI bahosi bo'lsa o'sha, aks holda keyword ball.

    Shakli `ai_scorer` da kafolatlangan, lekin saralash — butun hisobot
    o'tadigan yagona tor joy: bu yerdagi `TypeError` bitta vakansiyani emas,
    kunlik hisobotni butunlay yo'q qiladi. Shuning uchun himoya takrorlangan.
    """
    ai = v.get("ai")
    if isinstance(ai, dict) and isinstance(ai.get("score"), int):
        return ai["score"]
    return v.get("score", 0)


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
    picked.sort(key=lambda v: -rank(v))
    return picked


def build_health_block() -> str:
    """Manbalar holati — har hisobot oxirida.

    Shu blok bo'lmasa "bugun ish yo'q" bilan "scraper sindi" bir xil ko'rinadi:
    ikkalasida ham hisobot bo'sh keladi. Qarang: health.py.
    """
    lines = []
    summary = health.summary()
    if summary:
        lines.append(escape(summary))
    problems = health.alerts()
    if problems:
        lines.append("")
        lines.append("⚠️ <b>Manbalarda muammo:</b>")
        lines.extend(escape(p) for p in problems)
    return "\n".join(lines)


def build_crash_report(exc: BaseException) -> str:
    """Agent butunlay yiqilganda Telegram'ga ketadigan xabar.

    `health.py` manba darajasidagi jimgina yiqilishni yopdi, lekin run
    darajasida teshik ochiq qolgan edi: pipeline'ning istalgan joyidagi
    ushlanmagan istisno jarayonni o'ldirar, Telegram esa **umuman jim
    qolardi**. Endi avval sabab yuboriladi, keyin istisno qayta ko'tariladi
    (GitHub Actions run'i ham qizil bo'lsin).
    """
    lines = [
        "🚨 <b>Agent yiqildi</b> — bugungi hisobot tayyorlanmadi.",
        "",
        f"<b>{escape(type(exc).__name__)}</b>: {escape(str(exc)[:300])}",
    ]
    frames = traceback.extract_tb(exc.__traceback__)
    if frames:
        last = frames[-1]  # xato aynan qayerda ko'tarilgani
        lines.append(
            f"📍 {escape(os.path.basename(last.filename))}:{last.lineno}"
            f" — {escape(last.name)}()"
        )
    diagnostics = build_health_block()
    if diagnostics:
        # Qaysi manbalar ishga tushib ulgurgani — xatoni lokalizatsiya qiladi
        lines.append("")
        lines.append(diagnostics)
    return "\n".join(lines)


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
        # Ballsiz "tahlil" ni AI bahosi deb ko'rsatish yolg'on bo'lardi:
        # keyword ball AI baliday ko'rinib qolardi. Shubhali bo'lsa — keyword.
        if not (isinstance(ai, dict) and isinstance(ai.get("score"), int)):
            ai = None
        emoji = VERDICT_EMOJI.get(ai.get("verdict"), "⚪") if ai else "⚪"
        lines.append(f"{emoji} <b>{i}. {escape(v['title'][:70])}</b>")
        meta = " | ".join(filter(None, [v["source"], v["company"], v["salary"]]))
        if meta:
            lines.append(f"   {escape(meta)}")
        if ai:
            reason = ai.get("reason") or ""
            tip = ai.get("cv_tip") or ""
            # Sababsiz ball ham foydali — bo'sh tire qo'shib chalkashtirmaymiz
            head = f"   AI: {ai['score']}/100"
            lines.append(f"{head} — {escape(reason)}" if reason else head)
            if tip:
                lines.append(f"   💡 CV: {escape(tip)}")
        else:
            lines.append(f"   Keyword ball: {v['score']}/100")
        # Uzun havola o'rniga bosiladigan matn
        lines.append(f'   <a href="{escape(v["url"], quote=True)}">🔗 Vakansiyani ko\'rish</a>\n')

    if stats:
        top = ", ".join(f"{k} ({n})" for k, n in list(stats.items())[:8])
        lines.append(f"📈 <b>Bugun eng ko'p so'ralgan skillar:</b> {top}")

    diagnostics = build_health_block()
    if diagnostics:
        lines.append("\n" + diagnostics)

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


def configured() -> bool:
    """Telegram'ga yuborish umuman sozlanganmi.

    Sozlanmagan bo'lsa `send()` hisobotni konsolga chiqaradi va `False`
    qaytaradi — bu lokal ishlashda kutilgan holat, nosozlik emas. Chaqiruvchi
    ikkalasini farqlay olishi kerak: "Telegram yiqildi" bilan "Telegram
    ulanmagan" bir xil javob bo'lsa, lokal har bir run xato bilan tugardi.
    """
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def send(text: str) -> bool:
    """Xabarni Telegram'ga yuboradi. Yetkazilgan bo'lsa `True`.

    `send()` ataylab istisno ko'tarmaydi — bitta yuborilmagan xabar butun
    run'ni o'ldirmasligi kerak. Lekin shu sababli yiqilish ham muvaffaqiyat
    kabi ko'rinardi: chaqiruvchi "chaqirdim" bilan "yetkazildi" ni farqlay
    olmasdi. Endi farqlay oladi — yiqilish xabari uchun bu hal qiluvchi,
    chunki Actions'dagi zaxira bildirishnoma aynan shunga qarab ishlaydi.
    """
    if not configured():
        log.warning("Bot token/chat_id yo'q — hisobot konsolga chiqarildi:\n%s", text)
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    delivered = True
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
                delivered = False
        except Exception as e:
            log.error("Telegram yuborishda xato: %s", e)
            delivered = False
    return delivered
