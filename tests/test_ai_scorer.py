"""Chuqur tahlil: javob shakli kafolatlanadi, aks holda hisobot yiqiladi."""
import pytest
import requests

import config
import health
from scoring import ai_scorer

FULL = {"score": 82, "verdict": "topshirish_kerak", "reason": "Django", "cv_tip": "Fezot"}
KEYS = ["cv_tip", "reason", "score", "verdict"]


class TestClean:
    def test_valid_reply_survives_unchanged(self):
        assert ai_scorer._clean(dict(FULL)) == FULL

    def test_missing_keys_are_filled_in(self):
        result = ai_scorer._clean({"score": 82})
        assert sorted(result) == KEYS
        assert result["reason"] == ""

    def test_missing_verdict_is_rebuilt_from_the_score(self):
        """Ball bor ekan, butun tahlilni tashlash isrofgarchilik bo'lardi."""
        assert ai_scorer._clean({"score": 82})["verdict"] == "topshirish_kerak"
        assert ai_scorer._clean({"score": 50})["verdict"] == "urinib_korish"
        assert ai_scorer._clean({"score": 10})["verdict"] == "vaqt_sarflamaslik"

    def test_invented_verdict_is_replaced(self):
        assert ai_scorer._clean({"score": 30, "verdict": "juda_zor"})["verdict"] == \
            "vaqt_sarflamaslik"

    @pytest.mark.parametrize("raw,expected", [
        ("85", 85), ("85/100", 85), (82.6, 82), (5000, 100), (-20, 0), (0, 0),
    ])
    def test_score_is_coerced_and_clamped(self, raw, expected):
        assert ai_scorer._clean({"score": raw})["score"] == expected

    def test_object_wrapped_in_an_array(self):
        assert ai_scorer._clean([{"score": 50}])["score"] == 50

    def test_long_text_is_trimmed(self):
        result = ai_scorer._clean({"score": 50, "reason": "a" * 999})
        assert len(result["reason"]) == ai_scorer.TEXT_LIMIT

    @pytest.mark.parametrize("bad", [
        {"verdict": "topshirish_kerak"},   # ballsiz
        {"score": "yaxshi"},               # son emas
        {"score": True},                   # True == 1, lekin ball emas
        "82",                              # dict ham, list ham emas
        [],
        None,
    ])
    def test_unusable_replies_are_rejected(self, bad):
        """Ballsiz tahlil ma'nosiz: saralash ham, ko'rsatish ham unga tayanadi."""
        assert ai_scorer._clean(bad) is None


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def reply(text, stop_reason="end_turn"):
    return {"content": [{"type": "text", "text": text}], "stop_reason": stop_reason}


@pytest.fixture
def api(monkeypatch):
    """Anthropic javobini belgilaydigan fixture (haqiqiy so'rov yuborilmaydi)."""
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")

    def respond(payload):
        monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(payload))

    return respond


class TestAnalyze:
    @pytest.mark.parametrize("text,expected", [
        ('{"score": 88, "verdict": "topshirish_kerak", "reason": "r", "cv_tip": "c"}', 88),
        ('```json\n{"score": 70, "verdict": "urinib_korish", "reason": "r", "cv_tip": "c"}\n```', 70),
        ('Mana tahlil:\n{"score": 45}', 45),
        ('{"score": "77"}', 77),
    ])
    def test_usable_replies(self, api, vacancy, text, expected):
        api(reply(text))
        result = ai_scorer.analyze(vacancy())
        assert result["score"] == expected
        assert sorted(result) == KEYS

    @pytest.mark.parametrize("payload", [
        reply('{"score": 8', "max_tokens"),
        reply("Kechirasiz, javob bera olmayman."),
        reply('{"verdict": "topshirish_kerak"}'),
        {"type": "error", "error": {"message": "overloaded_error"}},
        {"content": []},
    ])
    def test_unusable_replies_return_none(self, api, vacancy, payload):
        api(payload)
        assert ai_scorer.analyze(vacancy()) is None

    def test_no_key_means_no_attempt(self, vacancy):
        assert ai_scorer.analyze(vacancy()) is None
        assert ai_scorer._stats["attempted"] == 0

    def test_missing_vacancy_field_does_not_disable_analysis(self, api, vacancy):
        """Kollektor bitta maydonni unutsa, har bir tahlil jimgina o'chib
        qolmasin — sarlavha va matn bo'lsa tahlil baribir ma'noli."""
        api(reply('{"score": 60}'))
        v = vacancy()
        del v["experience"]
        assert ai_scorer.analyze(v)["score"] == 60


class TestHealth:
    def test_healthy_run_has_no_alert(self):
        ai_scorer._stats.update(attempted=10, ok=10)
        ai_scorer.report_health()
        assert health.alerts() == []
        assert "ai-tahlil 10/10 ✅" in health.summary()

    def test_degraded_run_is_reported(self):
        """Keyword ballga qaytgan hisobot normal hisobotdan farq qilmaydi —
        aynan shuning uchun ogohlantirish kerak."""
        ai_scorer._stats.update(attempted=10, ok=3, first_error="ValueError: JSON yo'q")
        ai_scorer.report_health()
        assert len(health.alerts()) == 1
        assert health._entry("ai-tahlil").status == "degraded"

    def test_unused_ai_does_not_appear(self):
        ai_scorer.report_health()
        assert health.summary() == ""
