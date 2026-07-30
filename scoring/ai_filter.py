"""Gibrid filtrning 2-bosqichi: shubhali e'lonlarni Haiku bilan tasniflash.

keyword_check "uncertain" degan e'lonlar shu yerga keladi. Bir so'rovda
bir nechta e'lon birdan yuboriladi (batch) — xarajat kuniga ~1 sentdan kam.

AI ishlamasa (kalit yo'q, tarmoq xatosi) — fail-open: e'lon o'tkazib
yuboriladi, keyingi bosqichdagi keyword_scorer baribir saralaydi.
"""
import json
import logging
import requests

import config

log = logging.getLogger("ai_filter")
API_URL = "https://api.anthropic.com/v1/messages"

PROMPT = """Quyida raqamlangan ish e'lonlari. Har birini tasnifla:
- vacancy=true  — ish beruvchi xodim izlayapti (haqiqiy ish o'rni)
- vacancy=false — ish izlovchining rezyumesi, "sayt/bot yasab beraman" kabi \
xizmat taklifi, kurs/o'quv reklamasi yoki umuman ish o'rni bo'lmagan post

FAQAT quyidagi JSON massiv formatida javob ber, boshqa hech narsa yozma:
[{{"id": 1, "vacancy": true}}, {{"id": 2, "vacancy": false}}]

E'LONLAR:
{posts}"""


def _classify_batch(batch: list[dict]) -> dict[int, bool]:
    """Bitta API so'rov. Kalit — batch ichidagi indeks (0 dan)."""
    posts = "\n\n".join(
        f"#{i + 1}: {v['title']}\n{v['text'][:400]}" for i, v in enumerate(batch)
    )
    resp = requests.post(
        API_URL,
        headers={
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": PROMPT.format(posts=posts)}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()["content"][0]["text"]
    raw = raw.replace("```json", "").replace("```", "").strip()
    return {item["id"] - 1: bool(item["vacancy"]) for item in json.loads(raw)}


def classify(vacancies: list[dict]) -> dict[int, bool]:
    """Har bir e'lon indeksi uchun True (ish o'rni) / False qaytaradi.

    AI xato bersa yoki limitdan oshsa, o'sha indekslar dict'da bo'lmaydi —
    chaqiruvchi tomon ularni o'tkazib yuborishi kerak (fail-open).
    """
    if not (config.AI_FILTER_ENABLED and config.ANTHROPIC_API_KEY):
        return {}
    results: dict[int, bool] = {}
    capped = vacancies[: config.AI_FILTER_MAX_POSTS]
    if len(vacancies) > len(capped):
        log.warning(
            "AI filtr limiti: %d ta e'londan faqat %d tasi tasniflanadi",
            len(vacancies), len(capped),
        )
    for start in range(0, len(capped), config.AI_FILTER_BATCH_SIZE):
        batch = capped[start : start + config.AI_FILTER_BATCH_SIZE]
        try:
            verdicts = _classify_batch(batch)
            results.update({start + i: ok for i, ok in verdicts.items()})
        except Exception as e:
            log.error("AI tasniflashda xato (batch %d): %s", start, e)
    log.info(
        "AI filtr: %d ta shubhali e'londan %d tasi ish o'rni deb topildi",
        len(results), sum(results.values()),
    )
    return results
