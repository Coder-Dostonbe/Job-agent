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

# Qidiruv so'rovlari (hh, olx uchun)
SEARCH_QUERIES = ["python", "django", "backend"]

# hh.uz sozlamalari
HH_AREA_ID = "97"  # Uzbekistan
HH_DESC_LIMIT = 40  # nechta vakansiyaning to'liq matni yuklansin (har biri +1 so'rov)

# Kuzatiladigan Telegram ish kanallari (username, @siz)
TG_CHANNELS = [
    "UstozShogird",
    "itjobsuz",
    "python_jobs_uz",
]
TG_LOOKBACK_HOURS = 26  # oxirgi necha soatlik postlar o'qiladi

# OLX qidiruv sahifalari
OLX_URLS = [
    "https://www.olx.uz/rabota/it-telekom-kompyutery/?q=python",
    "https://www.olx.uz/rabota/it-telekom-kompyutery/?q=django",
]

# Scoring
AI_SCORE_THRESHOLD = 55
AI_MAX_VACANCIES = 6
REPORT_MIN_SCORE = 40

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
DB_PATH = os.getenv("DB_PATH", "vacancies.db")
# Telethon string session (GitHub Actions uchun — phone auth kerak emas)
TG_SESSION_STRING = os.getenv("TG_SESSION_STRING", "")
