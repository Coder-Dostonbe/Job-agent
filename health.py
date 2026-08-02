"""Manba salomatligi — "scraper sindi" ni "bugun ish yo'q" dan ajratadi.

Muammo: hh.uz HTML tuzilishini o'zgartirsa, kollektor xatoni loglab bo'sh
ro'yxat qaytarardi va Telegram'ga o'sha-o'sha "Bugun yangi mos vakansiya
topilmadi" xabari kelardi. Ya'ni sinib qolgan agent normal ishlayotgan
agentdan tashqi ko'rinishi bilan farq qilmasdi — haftalab sezilmay ketishi
mumkin edi.

Yechim: har bir kollektor ishlashi davomida shu modulga xabar beradi —
nechta e'lon ko'rdi, nechtasi natijaga kirdi, qanday xatolar bo'ldi, manba
umuman o'tkazib yuborildimi. Run oxirida `summary()` hisobot oxiriga
qo'shiladigan bir qatorni, `alerts()` esa e'tibor talab qiladigan
muammolar ro'yxatini beradi.

`scanned` va `kept` ataylab alohida:
    scanned — manbadan umuman o'qilgan e'lon/post soni
    kept    — kalit so'z filtridan o'tib natijaga kirgani
Telegram uchun ikkalasi farq qiladi: kanallar o'qildi (scanned > 0), lekin
"python/django/backend" bo'yicha hech nima mos kelmadi (kept == 0) — bu
normal holat, ogohlantirish emas. hh.uz va OLX uchun ikkalasi teng.
"""
import logging
from dataclasses import dataclass, field

log = logging.getLogger("health")

# Xato matnini logda to'liq qoldiramiz, hisobotga esa qisqartirib chiqaramiz
ERROR_SNIPPET = 240


@dataclass
class SourceHealth:
    name: str
    scanned: int = 0
    kept: int = 0
    errors: list[str] = field(default_factory=list)
    skipped: str = ""  # bo'sh bo'lmasa — manba umuman ishga tushmadi
    # Quyidagi ikkisi sanoq bilan o'lchanmaydigan komponentlar uchun (ombor
    # kabi): u "nechta e'lon qaytardi" degan savolga javob bermaydi, uning
    # holati — qaysi backend ishlayotgani.
    live: bool = False
    detail: str = ""  # xulosa qatorida son o'rniga chiqadi

    @property
    def status(self) -> str:
        if self.skipped:
            return "skipped"
        if self.errors:
            # Xato bor-u natija ham bor — qisman ishladi (masalan 6 kanaldan
            # bittasi o'qilmadi). Natija umuman yo'q bo'lsa — to'liq yiqilgan.
            return "degraded" if (self.scanned or self.live) else "failed"
        if self.live:
            return "ok"  # sanoqsiz komponent: ishladi, xato yo'q
        if not self.scanned:
            # Xatosiz nol natija — eng shubhali holat: so'rov muvaffaqiyatli
            # ketdi, lekin hech nima qaytmadi. Odatda selector/tuzilma o'zgargan.
            return "empty"
        if not self.kept:
            return "filtered"  # o'qildi, lekin mos kelmadi — normal
        return "ok"


STATUS_EMOJI = {
    "ok": "✅",
    "filtered": "➖",
    "empty": "⚠️",
    "degraded": "⚠️",
    "failed": "❌",
    "skipped": "⏭",
}

# Ogohlantirish talab qiladigan holatlar
BAD_STATUSES = {"empty", "degraded", "failed", "skipped"}

_sources: dict[str, SourceHealth] = {}


def reset() -> None:
    """Holatni tozalaydi (testlar va bitta jarayonda takroriy run uchun)."""
    _sources.clear()


def _entry(source: str) -> SourceHealth:
    return _sources.setdefault(source, SourceHealth(source))


def expect(source: str) -> None:
    """Manbani ro'yxatga oladi.

    Kollektor boshida chaqiriladi: manba hech narsa yozib ulgurmay yiqilsa
    ham hisobotda ko'rinib tursin (yo'q manba — sezilmaydigan manba).
    """
    _entry(source)


def found(source: str, kept: int, scanned: int | None = None) -> None:
    """Natijani qayd etadi. `scanned` berilmasa `kept` ga teng deb olinadi."""
    entry = _entry(source)
    entry.kept += kept
    entry.scanned += kept if scanned is None else scanned


def alive(source: str, detail: str = "") -> None:
    """Sanoq bilan o'lchanmaydigan komponent ishlayotganini qayd etadi.

    Ombor uchun kerak: `found()` unga to'g'ri kelmaydi (u e'lon qaytarmaydi),
    lekin qayd etilmasa "xatosiz 0 ta natija" deb noto'g'ri ogohlantiriladi.
    `detail` — xulosa qatorida son o'rniga ko'rinadigan matn ("postgres").
    """
    entry = _entry(source)
    entry.live = True
    if detail:
        entry.detail = detail


def error(source: str, message: object) -> None:
    _entry(source).errors.append(str(message))


def skipped(source: str, reason: str) -> None:
    _entry(source).skipped = reason


def statuses() -> list[SourceHealth]:
    return list(_sources.values())


def summary() -> str:
    """Hisobot oxiriga qo'shiladigan bir qator: har manba nima qaytardi."""
    if not _sources:
        return ""
    parts = [
        f"{s.name} {s.detail or s.kept} {STATUS_EMOJI[s.status]}"
        for s in _sources.values()
    ]
    return "🩺 Manbalar: " + " | ".join(parts)


def alerts() -> list[str]:
    """E'tibor talab qiladigan muammolar. Bo'sh ro'yxat — hammasi joyida."""
    out = []
    for s in _sources.values():
        status = s.status
        if status not in BAD_STATUSES:
            continue
        if status == "skipped":
            out.append(f"⏭ {s.name}: o'tkazib yuborildi — {s.skipped}")
        elif status == "failed":
            out.append(
                f"❌ {s.name}: 0 ta natija, {len(s.errors)} ta xato — "
                f"{s.errors[0][:ERROR_SNIPPET]}"
            )
        elif status == "degraded" and s.live:
            # Sanoqsiz komponent — "N ta topildi" ma'nosiz, xatoning o'zi gapiradi
            out.append(f"⚠️ {s.name}: {s.errors[0][:ERROR_SNIPPET]}")
        elif status == "degraded":
            out.append(
                f"⚠️ {s.name}: {s.kept} ta topildi, lekin {len(s.errors)} ta xato — "
                f"{s.errors[0][:ERROR_SNIPPET]}"
            )
        else:  # empty
            out.append(
                f"⚠️ {s.name}: xatosiz 0 ta e'lon qaytardi — "
                f"sayt tuzilishi o'zgargan yoki bloklangan bo'lishi mumkin"
            )
    return out


def log_alerts() -> list[str]:
    """`alerts()` ni qaytaradi va ularni logga ham yozadi."""
    problems = alerts()
    for p in problems:
        log.warning("%s", p)
    if not problems:
        log.info("Barcha manbalar sog'lom: %s", summary())
    return problems
