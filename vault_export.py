"""Kunlik hisobotni Second Brain vault'iga xom manba sifatida yozadi.

Hisobot Telegram'da o'qiladi va o'sha yerda qolib ketadi: kompaniya nomlari,
maosh raqamlari, AI verdiktlari va skill statistikasi har kuni chatga tushadi
va bir hafta o'tmay qidirib bo'lmaydigan holga keladi. Vault esa aynan shu
ma'lumotni saqlash uchun qurilgan — `Raw/Sources/` xom dalil qatlami bo'lib,
uning ustidan Wiki notalari kompilyatsiya qilinadi.

Nega ma'lumot bazadan emas, aynan shu yerdan olinadi: `storage.py` faqat
`url, source, title, score, ai_score` ni saqlaydi. Kompaniya, maosh, AI sababi
va `cv_tip` hisobot qurilgan paytdagina mavjud — run tugashi bilan yo'qoladi.
Vaultga qimmatlisi esa aynan o'shalar.

Eksport ATAYLAB hisobot yuborilishidan **oldin** chaqiriladi: yozuv yiqilsa,
ogohlantirish o'sha kunning hisobotiga tushsin. Yuborishdan keyin chaqirilganda
xatoni faqat log ko'rardi, ya'ni vault oylab jimgina bo'sh qolishi mumkin edi.

Yoqilishi: `.env` da `VAULT_PATH` — vault ildiziga yo'l. Bo'sh bo'lsa modul
umuman ishga tushmaydi va hisobotda ham ko'rinmaydi (vaultsiz ishlatayotgan
odamga har kuni "vault" qatorini ko'rsatish — ma'nosiz shovqin).
"""
import logging
import os
import pathlib
import re
from datetime import date

import config
import health
import reporter

log = logging.getLogger("vault")

# Vault ichida xom manbalar shu yerda yashaydi (qarang: vault AGENTS.md).
SOURCES_DIR = ("Raw", "Sources")

VERDICT_LABEL = {
    "topshirish_kerak": "topshirish kerak",
    "urinib_korish": "urinib ko'rish",
    "vaqt_sarflamaslik": "vaqt sarflamaslik",
}


def enabled() -> bool:
    return bool(config.VAULT_PATH)


def _safe(text: str) -> str:
    """Matnni vault ichida zararsiz qiladi.

    Uch xil belgi Obsidian'da **ma'no kasb etadi** va e'lon sarlavhasidan
    kelib chiqqanda buzg'unchi bo'ladi:

    - `[[...]]` — wikilink. "Python [[Junior]]" degan sarlavha vaultda mavjud
      bo'lmagan notaga havola yasaydi va grafikni soxta tugunlar bilan
      to'ldiradi.
    - qator boshidagi `#` — sarlavha yoki teg. Bizning tuzilishimizni buzadi.
    - `---` alohida qatorda — frontmatter chegarasi.

    E'tibor bering, bu **tozalash emas, zararsizlantirish**: matn o'qilishi
    kerak bo'lgan holicha qoladi, faqat sintaktik kuchi olib tashlanadi.
    """
    text = text.replace("[[", "[ [").replace("]]", "] ]")
    text = re.sub(r"^\s*#", r"\\#", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*---\s*$", "—", text, flags=re.MULTILINE)
    return text.strip()


def _reference() -> str:
    """Manbaning kelib chiqishi — vault sxemasi buni talab qiladi.

    Actions'da ishlaganda aniq run'ga havola qoldiramiz: oradan oy o'tib
    "bu raqamlar qayerdan keldi" degan savol tug'ilsa, log hali ham turadi.
    """
    server = os.getenv("GITHUB_SERVER_URL", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return "job-agent — lokal run"


def _frontmatter(today: date) -> list[str]:
    """Vault sxemasidagi xom manba frontmatter'i (Schema/frontmatter-schema.md).

    `Processed: false` — bu fayl hali kompilyatsiya qilinmagan xom dalil.
    Uni `true` ga o'zgartirish vault tomonining ishi: Wiki notasi yozilgandan
    keyin `wiki_tool.py source-scan --update` shuni qiladi. Agent o'zi
    belgilamaydi — yozilmagan notani "qayta ishlangan" deb ko'rsatish
    vaultdagi eng muhim invariantni buzadi.
    """
    return [
        "---",
        f'Title: "Ish bozori digesti — {today.isoformat()}"',
        'Author: "job-agent"',
        f'Reference: "{_reference()}"',
        "ContentType:",
        '  - "markdown"',
        f"Created: {today.isoformat()}",
        "Processed: false",
        "tags:",
        '  - "source"',
        "---",
    ]


def _vacancy_block(i: int, v: dict) -> list[str]:
    """Bitta vakansiya — kompilyatsiya uchun o'qish qulay bo'lgan shaklda."""
    lines = [f"### {i}. {_safe(v['title'])}", ""]

    meta = [f"- Manba: {_safe(v['source'])}"]
    if v.get("company"):
        meta.append(f"- Kompaniya: {_safe(v['company'])}")
    if v.get("salary"):
        meta.append(f"- Maosh: {_safe(v['salary'])}")
    if v.get("experience"):
        meta.append(f"- Tajriba: {_safe(v['experience'])}")
    meta.append(f"- Keyword ball: {v.get('score', 0)}")

    ai = v.get("ai")
    if isinstance(ai, dict) and isinstance(ai.get("score"), int):
        verdict = VERDICT_LABEL.get(ai.get("verdict"), ai.get("verdict") or "—")
        meta.append(f"- AI ball: {ai['score']}/100 ({_safe(str(verdict))})")
    elif not v.get("text"):
        # Hisobotdagi bilan bir xil ogohlantirish: tavsifsiz vakansiya deyarli
        # ballanmaydi, ya'ni uning past bali sifat haqida emas, ma'lumot
        # to'liqligi haqida gapiradi. Buni yozib qo'ymasak, oylar o'tib
        # tuzilgan statistika soxta xulosa beradi.
        meta.append("- Tavsif yuklanmadi — ball faqat sarlavha bo'yicha")

    meta.append(f"- URL: {v['url']}")
    lines += meta

    if isinstance(ai, dict):
        if ai.get("reason"):
            lines += ["", f"AI izohi: {_safe(str(ai['reason']))}"]
        if ai.get("cv_tip"):
            lines.append(f"CV maslahati: {_safe(str(ai['cv_tip']))}")
    lines.append("")
    return lines


def render(shown: list[dict], stats: dict, total_new: int,
           total_matched: int, low: list[dict] | None = None,
           not_a_job: int = 0, today: date | None = None) -> str:
    """Kunlik digestning Markdown matni.

    `reporter.build_report()` dan alohida turadi va shunday bo'lishi kerak:
    u Telegram uchun HTML yozadi, bu yerda esa Obsidian uchun Markdown kerak.
    Bittasini ikkinchisiga moslashtirish har ikkala formatni ham buzadi.
    """
    today = today or date.today()
    low = low or []
    lines = _frontmatter(today)
    lines += [
        "",
        f"# Ish bozori digesti — {today.isoformat()}",
        "",
        f"- Yangi e'lonlar: {total_new} ta",
        f"- Mos kelganlari ({config.REPORT_GOOD_SCORE}+ ball): {total_matched} ta",
        f"- Hisobotga tushgani: {len(shown)} ta",
        f"- Ish o'rni emas deb rad etilgani: {not_a_job} ta",
        "",
    ]

    if shown:
        lines += ["## Asosiy ro'yxat", ""]
        for i, v in enumerate(shown, 1):
            lines += _vacancy_block(i, v)

    if low:
        # Past ballilar to'liq yoziladi — hisobotdagi REPORT_LOW_LIMIT
        # qisqartmasi Telegram xabari uzunligi uchun kerak edi, faylda esa
        # bunday cheklov ma'nosiz. Aynan shu ro'yxat oylar o'tib "bozor nima
        # so'rayapti" degan savolga javob beradi.
        lines += ["## Past ballilar", ""]
        for v in low:
            lines.append(
                f"- [{v.get('score', 0):+d}] {_safe(v['title'])} "
                f"({_safe(reporter.source_group(v))}) — {v['url']}"
            )
        lines.append("")

    if stats:
        lines += ["## Bugun so'ralgan skillar", ""]
        lines += [f"- {_safe(k)}: {n}" for k, n in stats.items()]
        lines.append("")

    diagnostics = health.summary()
    if diagnostics:
        lines += ["## Manbalar holati", "", diagnostics, ""]
        problems = health.alerts()
        if problems:
            # Nosoz kunni belgilab qo'yamiz: yarim sinib turgan scraper bergan
            # raqamlarni keyinchalik trend deb o'qish — xato xulosaning eng
            # oson yo'li.
            lines += [""] + [f"- {_safe(p)}" for p in problems] + [""]

    return "\n".join(lines).rstrip() + "\n"


def export(shown: list[dict], stats: dict, total_new: int,
           total_matched: int, low: list[dict] | None = None,
           not_a_job: int = 0) -> pathlib.Path | None:
    """Digestni vaultga yozadi. Yozilgan fayl yo'li, yoki `None`.

    Hech qachon istisno ko'tarmaydi. Vault — hisobotning yon mahsuloti:
    diskda joy qolmagani yoki yo'l noto'g'ri yozilgani kunlik hisobotni
    yo'qotishga arzimaydi. Lekin jim ham qolmaydi — xato hisobotning
    diagnostika blokiga chiqadi.
    """
    if not enabled():
        return None

    today = date.today()
    # Fayl nomi sanaga bog'langan, ya'ni kun ichidagi takroriy run avvalgisini
    # yangilaydi, ikkinchi nusxa yaratmaydi. Bu muhim: hisobot yetkazilmasa
    # run yiqiladi va qo'lda qayta ishga tushiriladi.
    target = pathlib.Path(config.VAULT_PATH).joinpath(*SOURCES_DIR) / \
        f"Ish bozori digesti {today.isoformat()}.md"
    try:
        if not target.parent.is_dir():
            # Papkani o'zimiz yaratmaymiz. Yo'l xato yozilgan bo'lsa (masalan
            # eski vault manzili), `mkdir` uni jimgina "muvaffaqiyat" qilib
            # ko'rsatardi: fayllar hech kim qaramaydigan yangi papkaga oqib
            # ketaverardi. Mavjud bo'lmagan vault — sozlama xatosi.
            raise FileNotFoundError(f"vault papkasi topilmadi: {target.parent}")
        text = render(shown, stats, total_new, total_matched, low, not_a_job, today)
        target.write_text(text, encoding="utf-8")
    except Exception as e:
        health.alive("vault", detail="yozilmadi")
        health.error("vault", f"{type(e).__name__}: {e}")
        log.exception("Vaultga yozib bo'lmadi")
        return None

    health.alive("vault", detail=target.name)
    log.info("Vaultga yozildi: %s", target)
    return target
