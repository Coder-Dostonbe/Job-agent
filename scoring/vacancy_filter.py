"""E'lon turini ajratish: haqiqiy vakansiyami yoki ish izlovchi / xizmat taklifi.

Muammo: Telegram kanallarda (ayniqsa UstozShogird) va OLX'da ish beruvchilar
vakansiyalari bilan birga ish izlovchilarning rezyumelari va "sayt/bot yasab
beraman" kabi xizmat takliflari ham chiqadi. Bizga faqat ish o'rinlari kerak.

Gibrid yondashuv (1-bosqich — shu modul, bepul keyword tekshiruv):
- "vacancy"   → aniq ish o'rni, o'tkaziladi
- "seeker"    → aniq izlovchi/xizmat e'loni, rad etiladi
- "uncertain" → keyword'lar aniq javob bermadi — 2-bosqichga (ai_filter,
  Haiku klassifikatsiyasi) yuboriladi.

Bundan alohida `role_check()` bor: u e'lon **turini** emas, **rolini** ajratadi.
"Продукт-менеджер", "Директор департамента разработки", "Менеджер отдела
B2B-продаж" — bularning hammasi haqiqiy vakansiya, ya'ni yuqoridagi filtrdan
bemalol o'tadi, lekin dasturlash ishi emas. Ular hisobotda joy egallab, chinakam
vakansiyalarni pastga surib turardi.
"""

# Ish izlovchi yoki o'z xizmatini taklif qilayotgan odam belgilari
SEEKER_MARKERS = [
    # o'zbekcha — ish izlovchi
    "ish qidiryapman", "ish qidirayapman", "ish qidirmoqdaman",
    "ish izlayapman", "ish izlamoqdaman", "ish izlayabman",
    "ish joyi kerak", "ish kerak", "ishga joylashmoqchi",
    "ustoz kerak", "ish beruvchi kerak", "o'zim haqimda", "uzim haqimda",
    # o'zbekcha — xizmat / buyurtma taklifi
    "xizmat ko'rsataman", "xizmat kursataman", "xizmatlarim", "xizmatlar:",
    "yasab beraman", "qilib beraman", "tuzib beraman", "yozib beraman",
    "ochib beraman", "ishlab chiqib beraman", "sozlab beraman",
    "chiqarib beraman", "o'rnatib beraman",
    "buyurtma olaman", "buyurtma qabul", "buyurtmaga", "buyurtma asosida",
    "zakaz olaman", "zakazga", "narxi kelishiladi",
    "o'rgataman", "urgataman",  # birlik shaxs = kurs/xizmat sotish
    # ruscha — ish izlovchi / xizmat
    "ищу работу", "ищу заказ", "ищу проект", "в поиске работы",
    "ищу клиент", "мое резюме", "моё резюме",
    "предлагаю услуги", "окажу услуги", "выполню", "сделаю на заказ",
    "готов выполнить", "принимаю заказы", "разработаю для вас",
    "на заказ", "под заказ", "научу", "обучаю",
    # inglizcha
    "looking for a job", "looking for job", "open to work", "#opentowork",
    "available for hire", "for hire", "my services", "i will build",
    "i offer", "seeking a job", "seeking job",
]

# Haqiqiy vakansiya (ish beruvchi) belgilari
VACANCY_MARKERS = [
    # o'zbekcha
    "xodim kerak", "hodim kerak", "xodim izlaymiz", "xodim olamiz",
    "ishga olamiz", "ishga taklif", "ishga qabul", "ishchi kerak",
    "shogird kerak", "vakansiya", "bo'sh ish o'rni", "bosh ish o'rni",
    "talablar", "vazifalar", "mas'uliyat", "masuliyat",
    "maosh", "oylik", "ish haqi", "jamoamizga", "kompaniyamizga",
    "rezyume yuboring", "rezyumeni yuboring", "cv yuboring",
    # ruscha
    "вакансия", "требуется", "требования", "обязанности",
    "зарплата", "оклад", "з/п", "ищем сотрудника", "ищем разработчика",
    "ищем специалиста", "в команду", "в нашу команду",
    "отправляйте резюме", "присылайте резюме", "ждем ваше резюме",
    # inglizcha
    "hiring", "we are looking for", "job opening", "vacancy",
    "requirements", "responsibilities", "salary", "join our team",
    "send your cv", "send cv",
]


# Dasturlash bo'lmagan rollar. Bular **faqat sarlavhada** qidiriladi.
#
# Nega faqat sarlavha: haqiqiy dasturchi vakansiyasining **matnida** "отдел
# продаж", "менеджер проекта", "директор" so'zlari muntazam uchraydi — kimlar
# bilan ishlashi, kimga hisobot berishi tasvirlanadi. Rol esa deyarli har doim
# sarlavhada turadi.
#
# Topilsa nima bo'ladi: ilgari e'lon **butunlay rad etilardi**, shuning uchun
# ro'yxat ataylab tor edi — noto'g'ri atama butun vakansiyani jimgina yo'q
# qilardi. Endi u faqat `config.ROLE_PENALTY` ball jarimasi: e'lon past
# ballilar bo'limida ko'rinib turadi va qo'lda tekshirilishi mumkin. Xato
# qimmat bo'lmagani uchun ro'yxat kengaytirildi — quyidagi ikkinchi guruh
# aynan hisobotga o'tib ketgan haqiqiy e'lonlardan yig'ilgan.
#
# Tartib muhim: `role_check` birinchi mos kelgan atamani qaytaradi, shuning
# uchun aniq atamalar ("бизнес-аналитик") umumiylaridan ("аналитик") oldin
# turadi — logda foydali sabab ko'rinsin.
ROLE_REJECT = [
    # rahbariyat va boshqaruv
    "директор", "руководител", "начальник", "заведующ", "head of",
    "менеджер проект", "проджект", "project manager",
    "продакт", "продукт-менеджер", "продуктовый менеджер",
    "product manager", "product owner", "scrum",
    # savdo va marketing
    "продаж", "sales", "маркетолог", "маркетинг", "marketing",
    "smm", "таргетолог", "копирайт",
    "контент-менеджер", "контент менеджер", "бренд-менеджер", "pr-менеджер",
    # tahlil (dasturlash emas — texnik topshiriq yozadi)
    "бизнес-аналитик", "бизнес аналитик", "системный аналитик",
    "business analyst",
    # dizayn
    "дизайнер", "designer", "ux/ui", "ui/ux",
    # boshqa notexnik
    "рекрутер", "рекрутинг", "hr-менеджер", "hr менеджер", "эйчар",
    "бухгалтер", "юрист", "юрисконсульт", "секретар", "кассир",
    "офис-менеджер", "офис менеджер", "курьер", "консультант",
    "оператор", "колл-центр", "call-центр", "call center",
    "логист", "снабжен", "закупк", "системный администратор",
    # --- 2026-08-07: bazadagi haqiqiy e'lonlardan yig'ilgan ikkinchi guruh.
    # Hammasi hisobotning asosiy ro'yxatiga tushib qolgan edi (44–62 ball).
    "аналитик", "analyst",              # Портфельный/Стажер-аналитик, Аналитик SAP
    "преподавател", "o'qituvchi", "учител", "teacher",  # Ассистент преподавателя
    "информационной безопасности", "кибербезопасн", "kiberxavfsizlik",
    "governance", "compliance",         # AI Governance Specialist
    "администратор",                    # Администратор Jira, Confluence
    "тестировщик", "qa ", "quality assurance",
]


def role_check(title: str) -> str:
    """Sarlavha dasturlashdan boshqa rolni bildirsa — mos kelgan atamani qaytaradi.

    Bo'sh satr — e'lon o'tadi. Qaytarilgan atama chaqiruvchi tomonda logga
    yoziladi, ya'ni nima sababdan tashlangani har doim ko'rinib turadi.
    """
    low = _normalize(title)
    for term in ROLE_REJECT:
        if term in low:
            return term
    return ""


def _normalize(text: str) -> str:
    return text.lower().replace("’", "'").replace("`", "'").replace("‘", "'")


def keyword_check(text: str) -> tuple[str, str]:
    """('vacancy'|'seeker'|'uncertain', sabab) qaytaradi."""
    low = _normalize(text)
    seeker_hits = [m for m in SEEKER_MARKERS if m in low]
    vacancy_hits = [m for m in VACANCY_MARKERS if m in low]

    if not seeker_hits and vacancy_hits:
        return "vacancy", f"vakansiya belgilari: {', '.join(vacancy_hits[:3])}"
    if seeker_hits and len(seeker_hits) >= len(vacancy_hits):
        return "seeker", "izlovchi/xizmat e'loni: " + ", ".join(seeker_hits[:3])
    # Belgilar umuman yo'q, yoki ikkala tomon aralash — AI hal qilsin
    return "uncertain", (
        f"aralash signal ({len(vacancy_hits)} vs {len(seeker_hits)})"
        if seeker_hits else "belgilar topilmadi"
    )
