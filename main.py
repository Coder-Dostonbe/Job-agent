"""Job Search Agent — asosiy fayl.

Ishga tushirish: python main.py
Har kuni cron/Railway orqali avtomatik ishlaydi.
"""
import asyncio
import logging
import pathlib

import config
import health
import storage
import reporter
from collectors import hh, olx, tg_channels
from scoring import keyword_scorer, ai_scorer, vacancy_filter, ai_filter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("main")

# Actions'dagi zaxira bildirishnoma shu faylni qidiradi (qarang:
# .github/workflows/daily-jobs.yml). Nomi o'zgarsa — o'sha yerda ham o'zgarsin.
CRASH_MARKER = ".crash-notified"


def _mark_crash_reported() -> None:
    """Workflow'ga "yiqilish haqida xabar allaqachon ketdi" degan belgi qoldiradi.

    Belgisiz zaxira bildirishnoma bitta yiqilish uchun ikkinchi xabar
    yuborardi. Belgi faqat xabar **yetkazilganda** qo'yiladi: yuborishga
    urinib, Telegram javob bermagan bo'lsa, zaxira o'z ishini qilishi kerak.
    """
    try:
        pathlib.Path(CRASH_MARKER).write_text("reported", encoding="utf-8")
    except OSError as e:
        # Yomon holat emas: eng ko'pi bilan bitta takroriy xabar keladi
        log.warning("Belgi fayli yozilmadi (%s) — Actions takroriy xabar yuborishi mumkin", e)


def _no_vacancies_report() -> str:
    """"Bugun hech nima yo'q" xabari — manbalar holati bilan birga.

    Diagnostikasiz bu xabar ikki xil holatni bir xil ko'rsatardi: haqiqatan
    yangi vakansiya yo'q va scraper sinib qolgan. Endi farqi ko'rinadi.
    """
    text = "📊 Bugun yangi mos vakansiya topilmadi."
    diagnostics = reporter.build_health_block()
    return f"{text}\n\n{diagnostics}" if diagnostics else text


async def run():
    # 1. YIG'ISH — uchala manba
    vacancies = []
    vacancies += hh.collect()
    vacancies += olx.collect()
    vacancies += await tg_channels.collect()
    log.info("Jami yig'ildi: %d", len(vacancies))
    health.log_alerts()

    # 2. YANGILARNI AJRATISH — filtrdan OLDIN.
    # Sabab: bir e'lon OLX'ning ikkala qidiruvida (python, django) chiqishi
    # mumkin. Avval URL bo'yicha dedup qilsak, AI'ga ikki marta yuborilmaydi.
    all_new = storage.filter_new(vacancies)
    log.info("Yangi (dedup'dan keyin): %d", len(all_new))
    if not all_new:
        reporter.send(_no_vacancies_report())
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
        reporter.send(_no_vacancies_report())
        return

    # 4. KEYWORD SCORING
    for v in new:
        v["score"], v["score_reasons"] = keyword_scorer.score(v)
    relevant = sorted(
        (v for v in new if v["score"] >= config.REPORT_MIN_SCORE),
        key=lambda v: -v["score"],
    )

    # 5. TANLASH — har manbaga kvota, umumiy chegara REPORT_LIMIT
    shown = reporter.select(relevant)
    log.info("Hisobotga tanlandi: %d ta (mos kelganlar: %d)", len(shown), len(relevant))

    # 6. AI SCORING — faqat hisobotga tushadiganlarning eng yaxshilari
    for v in shown[:config.AI_MAX_VACANCIES]:
        if v["score"] >= config.AI_SCORE_THRESHOLD:
            v["ai"] = ai_scorer.analyze(v)
    ai_scorer.report_health()

    # AI ball bo'lsa, saralashda ustunlik beramiz
    shown.sort(key=lambda v: -reporter.rank(v))

    # 7. SAQLASH + HISOBOT
    storage.save(all_new)  # rad etilganlar ham — takror tekshirilmasin
    stats = storage.skill_stats(new)
    reporter.send(reporter.build_report(shown, stats, len(new), len(relevant)))
    log.info("Hisobot yuborildi ✅")


def main() -> None:
    """Agentni ishga tushiradi va yiqilsa jimgina o'lib qolmasligini kafolatlaydi."""
    try:
        asyncio.run(run())
    except Exception as e:
        log.exception("Agent yiqildi")
        try:
            if reporter.send(reporter.build_crash_report(e)):
                _mark_crash_reported()
        except Exception:
            # Xabarchi ham yiqilsa — asl xato yo'qolmasin, faqat loglaymiz.
            # Belgi qo'yilmaydi: xabarni Actions'dagi zaxira yuborishi kerak.
            log.exception("Yiqilish haqida xabar yuborib bo'lmadi")
        raise  # Actions run'i ham muvaffaqiyatsiz deb belgilansin


if __name__ == "__main__":
    main()
