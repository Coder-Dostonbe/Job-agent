"""Agent sozlamalari — Doston profili asosida."""
import os

# .env faylini yuklaymiz (local test uchun)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============ PROFIL ============
PROFILE = {
    "name": "Doston",
    "role": "Junior Backend Developer",
    "location": "Tashkent",
    "experience_years": 1,  # kommersiya loyihalari (Fezot Shop) hisobga olingan
    "skills": [
        "python", "django", "drf", "django rest framework", "rest api",
        "postgresql", "docker", "jwt", "git", "linux", "telegram bot",
        "railway", "gunicorn", "sqlite", "oauth",
    ],
    "languages": ["uzbek", "russian", "english"],
    "summary": (
        "Junior backend developer. Python/Django/DRF. Real loyihalar: "
        "Fezot Shop (production e-commerce), Shop API (DRF+JWT+Docker+Railway), "
        "Ovoza (yangiliklar portali, OAuth, AJAX), Telegram botlar. "
        "JavaScript bilmaydi. O'zbek, rus, ingliz (B2) tillarini biladi."
    ),
}

# Qidiruv so'rovlari (hh, olx uchun).
# "AI-разработчик" — vaybkoder yo'nalishi. Ataylab ruscha: hh.uz'da bozor shu
# atamani ishlatadi ("AI-разработчик / вайбкодер"). Sinab ko'rilgan variantlar:
#   "vibe coding" → 80 ta, lekin ko'pi axlat (PPC specialist, SEO, community mgr)
#   "вайбкодер"   → 1 ta (juda tor)
#   "AI-разработчик" → 7 ta, aniqligi eng yaxshisi ← tanlandi
SEARCH_QUERIES = ["python", "django", "backend", "AI-разработчик"]

# hh.uz sozlamalari
HH_AREA_ID = "97"  # Uzbekistan
# Nechta vakansiyaning to'liq matni yuklansin (har biri +1 so'rov + pauza).
# Qaysi 25 tasi degani muhim edi: ilgari tasodifiy tanlanardi, endi sarlavha
# bali bo'yicha eng istiqbollilari olinadi (qarang: hh._priority). Limit 25 dan
# 40 ga ko'tarildi — run #36 da hh.uz 53 ta e'lon berdi va agent atigi 2 daqiqa
# ishladi, ya'ni bosqichdagi 15 daqiqalik limitgacha keng joy bor.
HH_DESC_LIMIT = 40
HH_REQUEST_DELAY = 2.0  # so'rovlar orasidagi pauza, soniya (bot himoyasi uchun)
AI_MIN_SUCCESS_RATIO = 0.7  # chuqur tahlilning shu ulushidan kami ishlasa —
                            # ogohlantirish. Tahlilsiz vakansiya keyword ball
                            # bilan ko'rsatiladi: hisobot bir xil ko'rinadi,
                            # lekin sifati sezilarli pasayadi.

HH_DESC_MIN_RATIO = 0.7 # tavsiflarning shu ulushidan kami yuklansa — ogohlantirish.
                        # Tavsifsiz vakansiya deyarli ballanmaydi (faqat sarlavha
                        # qoladi), shuning uchun sekin degradatsiya ham ko'rinsin.

# Kuzatiladigan Telegram ish kanallari (username, @siz).
# Yangi kanal qo'shishdan oldin tekshiring: t.me/s/<username> ochilishi va
# oxirgi posti yaqin kunlarda bo'lishi kerak.
# Olib tashlanganlar: "itjobsuz" (username mavjud emas),
# "python_jobs_uz" (oxirgi post 2025-07-15 — kanal tashlab ketilgan).
TG_CHANNELS = [
    "UstozShogird",
    "uzdev_jobs",
    "ishmi_ish",
    "techjobs_vakansiya",
    "ayti_jobs",
    "frontEndJobo",
]
TG_LOOKBACK_HOURS = 26  # oxirgi necha soatlik postlar o'qiladi

# OLX qidiruv sahifalari
OLX_URLS = [
    "https://www.olx.uz/rabota/it-telekom-kompyutery/?q=python",
    "https://www.olx.uz/rabota/it-telekom-kompyutery/?q=django",
]

# Sarlavha bo'yicha ham dedup qilinadigan manbalar. OLX'da bir e'lon o'chirilib
# qayta joylanadi yoki "ko'tariladi" — URL o'zgaradi, sarlavha o'sha qoladi.
# hh.uz uchun YOQMANG: u yerda turli kompaniyalar bir xil sarlavha bilan
# ("Python разработчик") e'lon beradi, ular haqiqatan boshqa vakansiya.
TITLE_DEDUP_SOURCES = {"olx.uz"}

# Scoring
AI_SCORE_THRESHOLD = 55
AI_MAX_VACANCIES = 6

# Ball chegarasi ATAYLAB yo'q. Ilgari `REPORT_MIN_SCORE = 40` bor edi va u
# `keyword_scorer` ning boshlang'ich bali bilan **bir xil** edi — ya'ni bironta
# mos skill topilmagan e'lon ham aynan chegarada turardi va "api" (+4), "bot"
# (+3) kabi zaif so'zlardan bittasi tegishi bilan hisobotga kirardi
# (`Портфельный аналитик` 52, `Администратор Jira` 47). Teskarisi ham bo'lardi:
# tavsifida `java`/`react` uchragan haqiqiy `Junior Programmer` 18 ball olib
# jimgina yo'qolardi va buni hech kim sezmasdi.
#
# Endi chegara emas, **tartib** ishlaydi: hamma topilgan vakansiya hisobotga
# tushadi, past ballilar esa alohida bo'limda qisqa ko'rsatiladi. Ball xato
# qo'yilgan bo'lsa ham vakansiya ko'rinib turadi va qo'lda tekshirilishi mumkin.
REPORT_GOOD_SCORE = 40    # shu balldan yuqorisi asosiy ro'yxatga (AI tahlili bilan),
                          # pasti "past ballilar" bo'limiga tushadi

# Rol filtri endi rad etmaydi — jarima qo'yadi. Menejer/dizayner e'loni ro'yxat
# tubiga tushadi, lekin ko'rinib turadi: filtr xato ishlagan kun bilinsin.
ROLE_PENALTY = -40

# Hisobot ro'yxati
REPORT_LIMIT = 20         # asosiy ro'yxatdagi maksimal vakansiya soni
REPORT_LOW_LIMIT = 30     # "past ballilar" bo'limidagi maksimal qator. Kuniga
                          # 10–20 ta yangi e'lon keladi, ya'ni amalda hammasi
                          # sig'adi; limit faqat g'ayrioddiy kunlar uchun.
REPORT_SOURCE_QUOTA = 7   # har bir manbaga kafolatlangan joy. hh.uz kuniga
                          # ~90 ta e'lon beradi va to'liq tavsifi borligi uchun
                          # ball bo'yicha ham ustun keladi — kvotasiz OLX va
                          # Telegram ro'yxatga umuman tushmay qoladi.
                          # Kvota to'lmasa, bo'sh joylar boshqa manbalarga o'tadi.

# Gibrid vakansiya-filtr (keyword + AI). Sinov muddati: 2026-07-30 dan.
# Batafsil: TAKLIFLAR.md
AI_FILTER_ENABLED = True      # shubhali e'lonlarni Haiku bilan tasniflash
AI_FILTER_BATCH_SIZE = 15     # bitta API so'rovga necha e'lon sig'adi
AI_FILTER_MAX_POSTS = 150     # kuniga AI'ga yuboriladigan maksimal e'lon
                              # (OLX ~40 + Telegram 3 kanal — 60 kam edi)

# ============ MAXFIY KALITLAR (.env yoki GitHub Secrets) ============
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TG_API_ID = os.getenv("TG_API_ID", "")
TG_API_HASH = os.getenv("TG_API_HASH", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Vakansiyalar tarixi. DATABASE_URL bo'lsa PostgreSQL, aks holda lokal SQLite.
# GitHub Actions har run'da toza mashina beradi — fayl saqlanmaydi, shuning
# uchun jadval bo'yicha ishlaganda DATABASE_URL bo'lishi shart.
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_PATH = os.getenv("DB_PATH", "vacancies.db")
# Neon kabi serverless bazalar uzoq turgandan keyin "uyg'onadi" — birinchi
# ulanish sekin bo'lishi normal. Bitta timeout uchun butun tarixni yo'qotib,
# SQLite'ga tushib qolmaslik uchun qayta urinamiz.
DB_CONNECT_RETRIES = 3   # jami necha marta urinish
DB_CONNECT_TIMEOUT = 10  # bitta urinishni kutish, soniya
DB_RETRY_DELAY = 2.0     # urinishlar orasidagi pauza (har safar ko'payadi)

# Keskin pasayishni sezish (trend.py). "0 ta natija" ni health.py ushlaydi;
# bu yerdagi chegaralar esa "nol emas, lekin odatdagidan ancha kam" holati
# uchun. Ular ataylab konservativ — noto'g'ri ogohlantirish foydalanuvchini
# butun diagnostikaga ishonmaydigan qilib qo'yadi.
TREND_HISTORY_RUNS = 7   # bazaviy chiziq necha oxirgi run'dan olinadi
TREND_MIN_RUNS = 3       # shundan kam tarix bo'lsa taqqoslanmaydi
TREND_DROP_RATIO = 0.5   # medianadan shu ulushdan past bo'lsa — ogohlantirish
TREND_MIN_BASELINE = 8   # kam natijali manbalarda tebranish normal, jim turamiz
# Telethon string session (GitHub Actions uchun — phone auth kerak emas)
TG_SESSION_STRING = os.getenv("TG_SESSION_STRING", "")
