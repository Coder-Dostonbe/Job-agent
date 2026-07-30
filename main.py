"""Job Search Agent — asosiy fayl.

Ishga tushirish: python main.py
Har kuni cron/Railway orqali avtomatik ishlaydi.
"""
import asyncio
import logging

import config
import storage
import reporter
from collectors import hh, olx, tg_channels
from scoring import keyword_scorer, ai_scorer, vacancy_filter, ai_filter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("main")


async def run():
    # 1. YIG'ISH — uchala manba
    vacancies = []
    vacancies += hh.collect()
    vacancies += olx.collect()
    vacancies += await tg_channels.collect()
    log.info("Jami yig'ildi: %d", len(vacancies))

    # 2. YANGILARNI AJRATISH — filtrdan OLDIN.
    # Sabab: bir e'lon OLX'ning ikkala qidiruvida (python, django) chiqishi
    # mumkin. Avval URL bo'yicha dedup qilsak, AI'ga ikki marta yuborilmaydi.
    all_new = storage.filter_new(vacancies)
    log.info("Yangi (dedup'dan keyin): %d", len(all_new))
    if not all_new:
        reporter.send("📊 Bugun yangi mos vakansiya topilmadi.")
        return

    # 3. FAQAT ISH O'RINLARI — gibrid filtr (keyword + AI, qarang: TAKLIFLAR.md)
    real_vacancies, uncertain = [], []
    for v in all_new:
        if v["source"] == "hh.uz":  # hh API faqat vakansiya qaytaradi
            real_vacancies.append(v)
            continue
        verdict, reason = vacancy_filter.keyword_check(f"{v['title']} {v['text']}")
        if verdict == "vacancy":
            real_vacancies.append(v)
        elif verdict == "seeker":
            log.info("Rad etildi (%s): %s", reason, v["title"][:60])
        else:
            uncertain.append(v)

    if uncertain:
        log.info("Shubhali e'lonlar AI'ga yuborilmoqda: %d ta", len(uncertain))
        ai_verdicts = ai_filter.classify(uncertain)
        for i, v in enumerate(uncertain):
            # AI javob bermagan indekslar o'tkazib yuboriladi (fail-open)
            if ai_verdicts.get(i, True):
                real_vacancies.append(v)
            else:
                log.info("Rad etildi (AI: ish o'rni emas): %s", v["title"][:60])

    log.info("Ish o'rni emas deb rad etildi: %d", len(all_new) - len(real_vacancies))
    new = real_vacancies
    if not new:
        # Rad etilganlar ham bazaga yoziladi — ertaga AI'ga qayta yuborilmasin
        storage.save(all_new)
        reporter.send("📊 Bugun yangi mos vakansiya topilmadi.")
        return

    # 4. KEYWORD SCORING
    for v in new:
        v["score"], v["score_reasons"] = keyword_scorer.score(v)
    relevant = sorted(
        (v for v in new if v["score"] >= config.REPORT_MIN_SCORE),
        key=lambda v: -v["score"],
    )

    # 5. AI SCORING — faqat eng yaxshilari (xarajat nazorati)
    for v in relevant[:config.AI_MAX_VACANCIES]:
        if v["score"] >= config.AI_SCORE_THRESHOLD:
            v["ai"] = ai_scorer.analyze(v)

    # AI ball bo'lsa, saralashda ustunlik beramiz
    relevant.sort(key=lambda v: -(v["ai"]["score"] if v.get("ai") else v["score"]))

    # 6. SAQLASH + HISOBOT
    storage.save(all_new)  # rad etilganlar ham — takror tekshirilmasin
    stats = storage.skill_stats(new)
    reporter.send(reporter.build_report(relevant, stats, len(new)))
    log.info("Hisobot yuborildi ✅")


if __name__ == "__main__":
    asyncio.run(run())
