"""2-bosqich: eng yaxshi vakansiyalarni Claude API bilan chuqur tahlil qilish.

`analyze()` ikki xil natija qaytaradi va uchinchisi yo'q:

* `None` — tahlil bo'lmadi (kalit yo'q, tarmoq xatosi, javob yaroqsiz).
* to'liq dict — `score` (0-100 butun son), `verdict`, `reason`, `cv_tip`
  **doimo** mavjud va to'g'ri turda.

Bu kafolat muhim: ilgari model javobi qanday bo'lsa shundayligicha
qaytarilardi. Bitta yetishmagan kalit (`ai["verdict"]`) yoki matn ko'rinishidagi
ball (`"85"`) hisobot yasashda `KeyError`/`TypeError` berardi — natijada
**butun kunlik hisobot** yo'qolardi, holbuki qolgan 19 ta vakansiya joyida edi.
"""
import logging
import re

import requests

import config
import health
from scoring import ai_json

log = logging.getLogger("ai")
API_URL = "https://api.anthropic.com/v1/messages"
SOURCE = "ai-tahlil"

VERDICTS = ("topshirish_kerak", "urinib_korish", "vaqt_sarflamaslik")
TEXT_LIMIT = 300  # reason/cv_tip uchun — hisobot qatori cho'zilib ketmasin

PROMPT = """Sen ish qidiruv bo'yicha maslahatchi agentsan. Quyida nomzod profili va bitta vakansiya bor.

NOMZOD PROFILI:
{profile}

VAKANSIYA:
Sarlavha: {title}
Kompaniya: {company}
Tajriba talabi: {experience}
Matn: {text}

Vazifa: nomzod shu vakansiyaga topshirsa, suhbatga chaqirilish ehtimolini baholab ber.
FAQAT quyidagi JSON formatida javob ber, boshqa hech narsa yozma:
{{"score": 0-100 oralig'ida son, "verdict": "topshirish_kerak" yoki "urinib_korish" yoki "vaqt_sarflamaslik", "reason": "1-2 jumlada o'zbekcha sabab", "cv_tip": "shu vakansiya uchun CV'da nimani ta'kidlash kerak, 1 jumla"}}"""

# Bir run davomidagi natija — oxirida health'ga bir marta xabar beriladi
_stats = {"attempted": 0, "ok": 0, "first_error": ""}


def reset_stats() -> None:
    _stats.update(attempted=0, ok=0, first_error="")


def _as_score(value) -> int | None:
    """Ballni butun songa keltiradi. Model "85", "85/100" yoki 85.0 yozishi
    mumkin — uchalasi ham yaroqli. Diapazon 0-100 ga qisiladi."""
    if isinstance(value, bool):  # True == 1, lekin bu ball emas
        return None
    if isinstance(value, (int, float)):
        number = int(value)
    elif isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if not match:
            return None
        number = int(match.group())
    else:
        return None
    return max(0, min(100, number))


def _verdict_from_score(score: int) -> str:
    """Model verdictni tashlab ketsa yoki o'ylab topsa — balldan tiklaymiz.
    Butun tahlilni ball borligida bekor qilish isrofgarchilik bo'lardi."""
    if score >= 70:
        return "topshirish_kerak"
    if score >= 40:
        return "urinib_korish"
    return "vaqt_sarflamaslik"


def _as_text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())[:TEXT_LIMIT]


def _clean(data) -> dict | None:
    """Model javobini hisobot ishonadigan shaklga keltiradi."""
    if isinstance(data, list):  # ba'zan bitta obyektni massivga o'rab yuboradi
        data = next((d for d in data if isinstance(d, dict)), None)
    if not isinstance(data, dict):
        return None
    score = _as_score(data.get("score"))
    if score is None:
        # Ballsiz tahlilning ma'nosi yo'q: saralash ham, ko'rsatish ham
        # unga tayanadi. Keyword ballga qaytgan ma'qul.
        return None
    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        verdict = _verdict_from_score(score)
    return {
        "score": score,
        "verdict": verdict,
        "reason": _as_text(data.get("reason")),
        "cv_tip": _as_text(data.get("cv_tip")),
    }


def _fail(title: str, reason: object) -> None:
    log.error("AI tahlilda xato (%s): %s", title[:40], reason)
    if not _stats["first_error"]:
        _stats["first_error"] = str(reason)


def analyze(vacancy: dict) -> dict | None:
    if not config.ANTHROPIC_API_KEY:
        return None
    _stats["attempted"] += 1
    try:
        resp = requests.post(
            API_URL,
            headers={
                "x-api-key": config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",  # arzon va tez — bu vazifaga yetarli
                # 300 ta token to'rtta maydonga (ayniqsa o'zbekcha matnga) tor
                # kelib, javob JSON o'rtasida kesilardi — kesilgan JSON esa
                # butunlay yaroqsiz.
                "max_tokens": 500,
                "messages": [{
                    "role": "user",
                    "content": PROMPT.format(
                        profile=config.PROFILE["summary"],
                        # .get(): yetishmagan maydon butun tahlilni o'chirib
                        # qo'ymasin — sarlavha va matn bo'lsa tahlil ma'noli
                        title=vacancy.get("title", ""),
                        company=vacancy.get("company") or "noma'lum",
                        experience=vacancy.get("experience") or "ko'rsatilmagan",
                        text=(vacancy.get("text") or "")[:2000],
                    ),
                }],
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = _clean(ai_json.parse(ai_json.content_text(resp.json())))
    except Exception as e:
        _fail(vacancy.get("title", "?"), f"{type(e).__name__}: {e}")
        return None
    if result is None:
        _fail(vacancy.get("title", "?"), "javobda yaroqli 'score' yo'q")
        return None
    _stats["ok"] += 1
    return result


def report_health() -> None:
    """Run oxirida chaqiriladi: AI tahlili qay darajada ishlagani hisobotga
    chiqsin. Jimgina yiqilgan AI — keyword ballga qaytgan, ya'ni sifati
    pasaygan, lekin tashqaridan bir xil ko'rinadigan hisobot demakdir."""
    attempted, ok = _stats["attempted"], _stats["ok"]
    if not attempted:
        return
    ratio = ok / attempted
    log.info("AI tahlili: %d/%d (%.0f%%)", ok, attempted, ratio * 100)
    health.alive(SOURCE, f"{ok}/{attempted}")
    if ratio < config.AI_MIN_SUCCESS_RATIO:
        health.error(
            SOURCE,
            f"chuqur tahlil {attempted} tadan faqat {ok} tasida ishladi — "
            f"qolganlari keyword ball bilan ko'rsatildi. "
            f"Birinchi xato: {_stats['first_error']}",
        )
