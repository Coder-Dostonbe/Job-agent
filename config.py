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
HH_DESC_LIMIT = 25      # nechta vakansiyaning to'liq matni yuklansin (har biri +1 so'rov)
HH_REQUEST_DELAY = 2.0  # so'rovlar orasidagi pauza, soniya (bot himoyasi uchun)
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
REPORT_MIN_SCORE = 40

# Hisobot ro'yxati
REPORT_LIMIT = 20         # hisobotdagi maksimal vakansiya soni
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
# Telethon string session (GitHub Actions uchun — phone auth kerak emas)
TG_SESSION_STRING = os.getenv("TG_SESSION_STRING", "")
