"""1-bosqich: tez va bepul keyword scoring (0–100 ball)."""
import config

# DIQQAT: tekshiruv oddiy `word in text` — ya'ni qism-so'z ham mos keladi.
# Qisqa so'zlarni yozmang ("ai" → "email", "main", "детали" ichida ham topiladi).
# Kerak bo'lsa bo'shliq qo'shing (masalan "java " — "javascript" ni ushlamasin).

# Mos keladigan skillar (+ ball)
POSITIVE = {
    "python": 12, "django": 15, "drf": 10, "rest": 6, "api": 4,
    "postgresql": 6, "postgres": 6, "docker": 6, "jwt": 4,
    "backend": 8, "бэкенд": 8, "junior": 12, "джуниор": 12,
    "стажер": 10, "intern": 10, "telegram": 4, "bot": 3,
    # Vaybkoding — AI yordamida ishlab chiqish. Doston uchun mos yo'nalish.
    "вайбкод": 20, "vibe cod": 20, "vibe-cod": 20,
    "ai-разработчик": 15, "ai разработчик": 15,
    "cursor": 8, "copilot": 8, "claude": 8, "llm": 8,
    "chatgpt": 6, "промпт": 6, "prompt": 6,
    "n8n": 6, "no-code": 5, "low-code": 5,
}

# Mos kelmaydigan talablar (- ball)
NEGATIVE = {
    "senior": -35, "сеньор": -35, "lead": -30, "тимлид": -30,
    "react": -15, "vue": -15, "angular": -15, "node": -15,
    "javascript": -10, "frontend": -12, "фронтенд": -12,
    "php": -20, "laravel": -20, "java ": -20, "c#": -20, ".net": -20,
    "golang": -20, "1с": -25, "5 лет": -20, "4 года": -15,
    "5 years": -20, "middle+": -15,
    # DevOps / infratuzilma — bizga kelmasin
    "devops": -35, "девопс": -35, "sysadmin": -30,
    "системный администратор": -30, "системный инженер": -25,
    "ansible": -25, "terraform": -25, "kubernetes": -20, "k8s": -20,
    "jenkins": -20, "ci/cd": -15,
    # Data engineer / analitika — bugungi hisobotda ko'p uchradi
    "data engineer": -35, "дата инженер": -35, "инженер данных": -35,
    "data scientist": -30, "дата сайентист": -30,
    "data analyst": -25, "аналитик данных": -25,
    "airflow": -25, "spark": -25, "hadoop": -25, "big data": -25,
    "dwh": -20, " etl": -20, "clickhouse": -15,
}


def score(vacancy: dict) -> tuple[int, list[str]]:
    """Ball va sabablar ro'yxatini qaytaradi."""
    text = f"{vacancy['title']} {vacancy['text']}".lower()
    total, reasons = 40, []  # neytral boshlang'ich ball

    for word, pts in POSITIVE.items():
        if word in text:
            total += pts
            reasons.append(f"+{pts} {word}")

    for word, pts in NEGATIVE.items():
        if word in text:
            total += pts
            reasons.append(f"{pts} {word}")

    # Django bor-u, boshqa til asosiy bo'lmasa — kuchli signal
    if "django" in text and "python" in text:
        total += 5
        reasons.append("+5 python+django juftligi")

    # Pastki chegara ataylab manfiy: ilgari `max(0, ...)` hamma yomon
    # variantni bir xil "0" ga aylantirardi va "biroz mos emas" bilan "umuman
    # boshqa kasb" farqlanmasdi. Endi ball qanchalik mos emasligini ham
    # ko'rsatadi — hisobotda hammasi ko'rinadigani uchun bu tartib muhim.
    return max(-100, min(100, total)), reasons
