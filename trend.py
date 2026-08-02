"""Keskin pasayishni sezish — nol emas, lekin g'alati kam natija.

`health.py` "xatosiz 0 ta natija" holatini yopdi. Lekin eng ko'p uchraydigan
sinish shakli nol emas: hh.uz sahifasining bir bo'limi o'zgaradi, kollektor
qolgan qismini o'qiy oladi va 63 ta o'rniga 6 ta e'lon qaytaradi. Hech qanday
istisno yo'q, xato yo'q, status ✅ — hisobot esa yarim bo'sh keladi va bu
"bugun bozorda tinch" ga o'xshab turadi.

Bunday holatni bitta run'ga qarab bilib bo'lmaydi: 6 ta ko'pmi yoki kammi
degan savolga javob faqat o'tmishda. Shuning uchun har run'dagi sonlar
`storage.record_counts()` bilan saqlanadi, keyingi run esa bugungi sonni
o'tgan run'lar **medianasi** bilan taqqoslaydi.

Nega median, o'rtacha emas: bitta yiqilgan kun (0 ta) o'rtachani pastga
tortadi va ertasiga haqiqiy pasayish sezilmay qoladi. Median bitta chetdagi
qiymatga befarq.

Ikkita ataylab qo'yilgan cheklov — noto'g'ri ogohlantirish foydalanuvchini
diagnostikaga ishonmaydigan qilib qo'yadi:

- `TREND_MIN_RUNS` — tarix kam bo'lsa taqqoslanmaydi (birinchi kunlar).
- `TREND_MIN_BASELINE` — odatda 3 ta beradigan manba 1 ta berishi normal
  tebranish, buni har safar ogohlantirsak shovqin bo'ladi.

Cheklov: agar manba ketma-ket past qolsa, median ham asta-sekin pasayadi va
ogohlantirish o'chadi ("yangi normal" muammosi). 7 run'lik oynada bu **4 kun**
ogohlantirgandan keyin sodir bo'ladi (5-kuni past qiymatlar 7 tadan 4 tasini
egallaydi va median ularga ko'chadi) — o'lchangan, `test_trend.py` da
mahkamlangan. Ya'ni bir marta emas, to'rt marta xabar keladi; e'tibor
berilmasa esa jimlik boshlanadi.
"""
import logging

import config
import health
import storage

log = logging.getLogger("trend")

# Ogohlantirishga sabab bo'lmaydigan statuslar: manba ishladi va natijasi bor.
# Qolganlari (empty/failed/skipped) allaqachon o'z ogohlantirishini beradi —
# ustiga trend xabarini qo'shish bir nosozlikni ikki marta aytish bo'lardi.
QUIET_STATUSES = ("ok", "filtered")


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def check(history: dict[str, list[int]], today: dict[str, int]) -> list[tuple[str, str]]:
    """(manba, ogohlantirish) juftliklari. Sof funksiya — sinash uchun qulay."""
    out = []
    for source, count in today.items():
        past = history.get(source, [])
        if len(past) < config.TREND_MIN_RUNS:
            continue
        baseline = _median(past)
        if baseline < config.TREND_MIN_BASELINE:
            continue
        if count >= baseline * config.TREND_DROP_RATIO:
            continue
        out.append((
            source,
            f"odatdagidan keskin kam: {count} ta "
            f"(oxirgi {len(past)} run medianasi — {baseline:.0f} ta). "
            f"Sayt tuzilishi qisman o'zgargan bo'lishi mumkin.",
        ))
    return out


def check_and_record() -> None:
    """Kollektorlar tugagach chaqiriladi: avval taqqoslaydi, keyin yozadi.

    Tartib muhim — bugungi son o'z bazaviy chizig'iga kirib qolmasligi kerak.
    """
    entries = [s for s in health.statuses() if not s.skipped and not s.live]
    counts = {s.name: s.scanned for s in entries}
    if not counts:
        return

    history = storage.recent_counts(config.TREND_HISTORY_RUNS)
    quiet = {s.name: s.scanned for s in entries if s.status in QUIET_STATUSES}
    for source, message in check(history, quiet):
        log.warning("%s: %s", source, message)
        health.warn(source, message)

    storage.record_counts(counts)
