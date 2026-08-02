"""E'lon filtri: bitta buzuq element butun guruhni yo'q qilmasin."""
import pytest
import requests

import config
import health
from scoring import ai_filter


class TestReadVerdicts:
    def test_normal_reply(self):
        data = [{"id": 1, "vacancy": True}, {"id": 2, "vacancy": False}]
        assert ai_filter._read_verdicts(data, 2) == {0: True, 1: False}

    def test_broken_item_is_dropped_not_the_batch(self):
        """Ilgari bitta yetishmagan `id` 15 talik guruhni butunlay yo'qotardi."""
        data = [{"id": 1, "vacancy": True}, {"vacancy": False}]
        assert ai_filter._read_verdicts(data, 2) == {0: True}

    @pytest.mark.parametrize("bad_id", [99, 0, -1, "abc", None])
    def test_out_of_range_id_is_dropped(self, bad_id):
        """Bu ehtiyotkorlik emas: o'ylab topilgan raqam boshqa e'lonning
        tasnifi bo'lib qo'llanib, uni noto'g'ri rad etishi mumkin edi."""
        data = [{"id": 1, "vacancy": True}, {"id": bad_id, "vacancy": False}]
        assert ai_filter._read_verdicts(data, 2) == {0: True}

    def test_string_id_is_accepted(self):
        assert ai_filter._read_verdicts([{"id": "2", "vacancy": True}], 2) == {1: True}

    def test_non_array_raises(self):
        with pytest.raises(ValueError):
            ai_filter._read_verdicts({"id": 1}, 2)

    def test_nothing_usable_raises(self):
        with pytest.raises(ValueError):
            ai_filter._read_verdicts([{"x": 1}], 2)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(config, "AI_FILTER_ENABLED", True)

    class FakeResponse:
        def __init__(self, text):
            self.text_ = text

        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"text": self.text_}], "stop_reason": "end_turn"}

    def respond(text):
        monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(text))

    return respond


class TestClassify:
    def test_verdicts_land_on_the_right_posts(self, api, vacancy):
        api('Mana natija:\n[{"id": 1, "vacancy": true}, {"id": 2, "vacancy": false}]')
        assert ai_filter.classify([vacancy(), vacancy()]) == {0: True, 1: False}
        assert health.alerts() == []

    def test_failure_is_fail_open_and_reported(self, api, vacancy):
        """Filtr yiqilsa e'lonlar o'tib ketaveradi — hisobotga rezyume va
        reklama aralashadi, shuning uchun sababi ko'rinib tursin."""
        api("umuman JSON emas")
        assert ai_filter.classify([vacancy(), vacancy()]) == {}
        assert len(health.alerts()) == 1
        assert "o'tkazib yuborildi" in health.alerts()[0]

    def test_disabled_filter_stays_out_of_the_report(self, vacancy):
        assert ai_filter.classify([vacancy()]) == {}
        assert health.summary() == ""

    def test_post_limit_is_respected(self, api, vacancy, monkeypatch):
        monkeypatch.setattr(config, "AI_FILTER_MAX_POSTS", 1)
        monkeypatch.setattr(config, "AI_FILTER_BATCH_SIZE", 15)
        api('[{"id": 1, "vacancy": true}]')
        assert ai_filter.classify([vacancy(), vacancy(), vacancy()]) == {0: True}
