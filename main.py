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
import trend
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


def _deliver(text: str) -> None:
    """Hisobotni yuboradi; yetkazilmasa run'ni yiqitadi.

    Ilgari `reporter.send()` natijasi umuman tekshirilmasdi. Telegram xabarni
    rad etsa (token almashtirilgan, chat bloklangan, HTML yaroqsiz), agent
    baribir "Hisobot yuborildi ✅" deb yozib, Actions run'i yashil bo'lib
    tugardi — ya'ni foydalanuvchi hisobot kelmaganini faqat sezib qolsa
    bilardi. Endi bu yiqilish: run qizil bo'ladi va workflow'dagi zaxira
    bildirishnoma ishga tushadi.

    Telegram umuman sozlanmagan bo'lsa (lokal ishlash) bu xato emas —
    hisobot konsolga chiqadi va run davom etadi.
    """
    if reporter.send(text) or not reporter.configured():
        return
    raise RuntimeError(
        "Hisobot Telegram'ga yetkazilmadi — sabab yuqoridagi loglarda "
        "(token, chat_id yoki xabar formati)"
    )


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
    # Nol bo'lmagan, lekin odatdagidan keskin kam natijani sezadi — dedup'dan
    # oldin, chunki taqqoslash manbaning xom qaytarganiga qarab bo'lishi kerak
    trend.check_and_record()
    health.log_alerts()

    # 2. YANGILARNI AJRATISH — filtrdan OLDIN.
    # Sabab: bir e'lon OLX'ning ikkala qidiruvida (python, django) chiqishi
    # mumkin. Avval URL bo'yicha dedup qilsak, AI'ga ikki marta yuborilmaydi.
    all_new = storage.filter_new(vacancies)
    log.info("Yangi (dedup'dan keyin): %d", len(all_new))
    if not all_new:
        _deliver(_no_vacancies_report())
        return

    # 3. FAQAT ISH O'RINLARI — gibrid filtr (keyword + AI, qarang: TAKLIFLAR.md)
    #
    # Bu bosqich e'lon **ish o'rnimi** degan savolga javob beradi: rezyume va
    # "sayt yasab beraman" kabi xizmat takliflari bu yerda tashlanadi. Ular
    # hisobotda umuman kerak emas — ularni ko'rsatish "mos kelmagan vakansiyani
    # qo'lda tekshirish" emas, shunchaki shovqin. Nechtasi tashlangani esa
    # hisobotda yoziladi, ya'ni filtr ortiqcha yeb qo'ysa bilinadi.
    #
    # Rolning mos-nomosligi (menejer, dizayner) esa BOSHQA savol — u endi bu
    # yerda hal qilinmaydi, quyida jarima bilan hal qilinadi.
    real_vacancies, uncertain = [], []
    flagged_roles = 0
    for v in all_new:
        # Rol tekshiruvi BARCHA manbalarga tegishli. hh.uz quyida turdagi
        # filtrdan ozod (u faqat vakansiya qaytaradi), lekin aynan hh.uz
        # "Продукт-менеджер" va "Директор департамента разработки" kabi
        # e'lonlarni eng ko'p olib keladi — ular haqiqiy vakansiya, shunchaki
        # dasturlash emas.
        v["role_flag"] = vacancy_filter.role_check(v["title"])
        if v["role_flag"]:
            flagged_roles += 1
            log.info("Rol mos emas ('%s'), ball pasaytiriladi: %s",
                     v["role_flag"], v["title"][:60])
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

    not_a_job = len(all_new) - len(real_vacancies)
    log.info("Ish o'rni emas deb rad etildi: %d ta; roli mos emas deb "
             "belgilandi: %d ta (ular hisobotda qoladi)", not_a_job, flagged_roles)
    new = real_vacancies
    if not new:
        _deliver(_no_vacancies_report())
        # Rad etilganlar ham bazaga yoziladi — ertaga AI'ga qayta yuborilmasin.
        # Yuborishdan KEYIN: yetkazilmagan bo'lsa yuqorida yiqilamiz va ertaga
        # hammasi qaytadan ko'riladi (ozgina AI xarajati — yo'qotishdan arzon).
        storage.save(all_new)
        return

    # 4. KEYWORD SCORING — chegara yo'q, hamma ball oladi
    for v in new:
        v["score"], v["score_reasons"] = keyword_scorer.score(v)
        if v.get("role_flag"):
            v["score"] += config.ROLE_PENALTY
            v["score_reasons"].append(
                f"{config.ROLE_PENALTY} dasturlash emas: {v['role_flag']}"
            )
    ranked = sorted(new, key=lambda v: -v["score"])
    good = [v for v in ranked if v["score"] >= config.REPORT_GOOD_SCORE]

    # 5. TANLASH — asosiy ro'yxatga har manbaga kvota, chegara REPORT_LIMIT.
    # Tanlanmaganlar yo'qolmaydi: ular pastdagi qisqa ro'yxatga tushadi.
    shown = reporter.select(good)
    # Aynan shu obyektlar bo'yicha (`id`), qiymat bo'yicha emas: ikki e'lonning
    # lug'ati tasodifan teng bo'lib qolsa, `in` ikkalasini ham yashirib qo'yardi.
    in_main = {id(v) for v in shown}
    low = [v for v in ranked if id(v) not in in_main]
    log.info("Asosiy ro'yxat: %d ta (%d balldan yuqori: %d ta), "
             "past ballilar ro'yxati: %d ta",
             len(shown), config.REPORT_GOOD_SCORE, len(good), len(low))

    # 6. AI SCORING — faqat hisobotga tushadiganlarning eng yaxshilari
    for v in shown[:config.AI_MAX_VACANCIES]:
        if v["score"] >= config.AI_SCORE_THRESHOLD:
            v["ai"] = ai_scorer.analyze(v)
    ai_scorer.report_health()

    # AI ball bo'lsa, saralashda ustunlik beramiz
    shown.sort(key=lambda v: -reporter.rank(v))

    # 7. HISOBOT, KEYIN SAQLASH
    # Tartib ataylab shunday. Ilgari avval saqlanardi: hisobot yetib bormasa
    # ham vakansiyalar "ko'rilgan" deb belgilanar va **boshqa hech qachon
    # ko'rsatilmasdi** — jimgina yo'qolgan kun. Endi yetkazilgani aniq bo'lgach
    # yoziladi.
    stats = storage.skill_stats(new)
    _deliver(reporter.build_report(shown, stats, len(new), len(good),
                                   low=low, not_a_job=not_a_job))
    storage.save(all_new)  # rad etilganlar ham — takror tekshirilmasin
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
