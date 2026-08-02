"""Testlar uchun umumiy izolyatsiya.

Ikkita xavf bor va ikkalasi ham jimgina yuz beradi:

1. **Haqiqiy secretlar.** `config.py` import paytida `load_dotenv()` chaqiradi.
   Lokal mashinada bu haqiqiy Neon URL'ini va Telegram tokenini yuklaydi —
   e'tiborsiz yozilgan test prod bazaga yozib yuborishi yoki sizga real xabar
   jo'natishi mumkin.
2. **Tarmoq.** Testda tasodifan qolib ketgan haqiqiy so'rov CI'ni sekin va
   beqaror qiladi, eng yomoni — pul sarflaydi (Anthropic).

Shuning uchun har bir testdan oldin config bo'shatiladi, baza vaqtinchalik
papkaga ko'chiriladi va tarmoq yopiladi. Tarmoq kerak bo'lgan test uni o'zi
`monkeypatch` bilan ochadi (autouse fixture avval ishlaydi).
"""
import pytest
import requests

import config
import health
import storage
from scoring import ai_scorer


def _blocked(*args, **kwargs):
    raise AssertionError(
        "Test tarmoqqa chiqmoqchi bo'ldi. Kerak bo'lsa requests.post/get ni "
        "monkeypatch bilan almashtiring."
    )


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(requests, "post", _blocked)
    monkeypatch.setattr(requests, "get", _blocked)

    health.reset()
    storage.reset_state()
    ai_scorer.reset_stats()
    yield
    health.reset()


@pytest.fixture
def vacancy():
    """Bitta vakansiya yasaydigan fabrika — maydonlarni kerakligicha almashtiring."""
    def make(**overrides):
        base = {
            "url": "https://example.test/1",
            "source": "hh.uz",
            "title": "Python dasturchi",
            "text": "django, postgresql",
            "company": "ACME",
            "salary": "",
            "experience": "1-3 yil",
            "score": 55,
        }
        base.update(overrides)
        return base

    return make
