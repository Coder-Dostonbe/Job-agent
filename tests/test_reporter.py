"""Hisobot yasash — bu yerdagi har qanday istisno butun kunni yo'q qiladi."""
import config
import health
import reporter


class TestRank:
    def test_ai_score_wins(self, vacancy):
        assert reporter.rank(vacancy(score=55, ai={"score": 90})) == 90

    def test_keyword_score_is_the_fallback(self, vacancy):
        assert reporter.rank(vacancy(score=55, ai=None)) == 55

    def test_broken_ai_score_does_not_raise(self, vacancy):
        """Matn ko'rinishidagi ball saralashda `TypeError` berardi."""
        assert reporter.rank(vacancy(score=55, ai={"score": "buzuq"})) == 55
        assert reporter.rank(vacancy(score=55, ai="dict emas")) == 55


class TestBuildReport:
    def test_malformed_ai_does_not_destroy_the_report(self, vacancy):
        """Ilgari yetishmagan `verdict` butun hisobotni yiqitardi."""
        broken = [
            vacancy(ai={"score": 82}),                    # verdict/reason/cv_tip yo'q
            vacancy(ai={"verdict": "topshirish_kerak"}),  # ball yo'q
            vacancy(ai="shunchaki matn"),                 # dict ham emas
            vacancy(ai=None),
            vacancy(),
        ]
        report = reporter.build_report(broken, {}, 5, 5)
        assert report.startswith("📊")
        assert report.count("🔗 Vakansiyani ko'rish") == 5

    def test_scoreless_analysis_is_not_dressed_up_as_an_ai_score(self, vacancy):
        report = reporter.build_report([vacancy(score=55, ai={"verdict": "x"})], {}, 1, 1)
        assert "Keyword ball: 55/100" in report
        assert "AI: 55/100" not in report

    def test_ai_text_is_html_escaped(self, vacancy):
        report = reporter.build_report([vacancy(ai={
            "score": 80, "verdict": "topshirish_kerak",
            "reason": "<script>alert(1)</script>", "cv_tip": "a & b",
        })], {}, 1, 1)
        assert "<script>" not in report
        assert "a &amp; b" in report

    def test_empty_reason_leaves_no_dangling_dash(self, vacancy):
        report = reporter.build_report(
            [vacancy(ai={"score": 80, "verdict": "topshirish_kerak",
                         "reason": "", "cv_tip": ""})], {}, 1, 1)
        assert "AI: 80/100\n" in report

    def test_health_block_is_appended(self, vacancy):
        health.expect("hh.uz")
        health.found("hh.uz", 63)
        assert "🩺 Manbalar" in reporter.build_report([vacancy()], {}, 1, 1)


class TestSelect:
    def test_quota_keeps_a_loud_source_from_crowding_others_out(self, vacancy, monkeypatch):
        """hh.uz kuniga ~90 ta e'lon beradi va ballari ham yuqori — oddiy
        "eng yaxshi N ta" ro'yxatda OLX va Telegram umuman ko'rinmay qolardi."""
        monkeypatch.setattr(config, "REPORT_SOURCE_QUOTA", 2)
        monkeypatch.setattr(config, "REPORT_LIMIT", 4)
        scored = [vacancy(source="hh.uz", score=90 - i, url=f"h{i}") for i in range(5)]
        scored += [vacancy(source="olx.uz", score=50, url="o1")]
        picked = reporter.select(scored)
        assert sum(1 for v in picked if v["source"] == "olx.uz") == 1

    def test_telegram_channels_count_as_one_source(self, vacancy):
        assert reporter.source_group(vacancy(source="t.me/python_jobs_uz")) == "telegram"
        assert reporter.source_group(vacancy(source="hh.uz")) == "hh.uz"


class TestCrashReport:
    def test_it_names_the_error_and_where_it_happened(self):
        try:
            raise KeyError("verdict")
        except Exception as e:
            crash = reporter.build_crash_report(e)
        assert "KeyError" in crash
        assert "test_reporter.py" in crash

    def test_it_carries_the_diagnostics(self):
        health.expect("hh.uz")
        health.found("hh.uz", 63)
        try:
            raise RuntimeError("boom")
        except Exception as e:
            crash = reporter.build_crash_report(e)
        assert "🩺 Manbalar" in crash

    def test_error_text_is_escaped(self):
        try:
            raise ValueError("selector <div class='x'> topilmadi & bo'sh")
        except Exception as e:
            crash = reporter.build_crash_report(e)
        assert "<div" not in crash
        assert "&lt;div" in crash


class TestSplit:
    def test_long_report_is_split_on_line_boundaries(self):
        """Telegram limiti 4096 belgi. HTML tegi o'rtasidan kesilmasin."""
        text = "\n".join(f'<a href="https://x/{i}">qator {i}</a>' for i in range(400))
        chunks = reporter._split(text)
        assert len(chunks) > 1
        assert all(len(c) <= 3900 + 100 for c in chunks)
        assert all(c.count("<a") == c.count("</a>") for c in chunks)


class TestSend:
    """`send()` yetkazilganini rostgo'y aytishi kerak.

    Ilgari u har doim `None` qaytarardi: Telegram 401 bersa ham, tarmoq
    uzilsa ham chaqiruvchi uchun natija muvaffaqiyat bilan bir xil edi.
    Yiqilish xabari uchun bu farq hal qiluvchi — Actions'dagi zaxira
    bildirishnoma aynan shunga qarab jim turadi yoki gapiradi.
    """

    class _Resp:
        def __init__(self, ok=True, status_code=200, text=""):
            self.ok, self.status_code, self.text = ok, status_code, text

    def _configure(self, monkeypatch):
        monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "sinov-token")
        monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")

    def test_delivered_message_returns_true(self, monkeypatch):
        self._configure(monkeypatch)
        monkeypatch.setattr(reporter.requests, "post",
                            lambda *a, **k: self._Resp())
        assert reporter.send("salom") is True

    def test_rejected_message_returns_false(self, monkeypatch):
        """Telegram 400/401 qaytarsa — xabar yetib bormagan."""
        self._configure(monkeypatch)
        monkeypatch.setattr(reporter.requests, "post",
                            lambda *a, **k: self._Resp(ok=False, status_code=401,
                                                       text="Unauthorized"))
        assert reporter.send("salom") is False

    def test_network_error_returns_false(self, monkeypatch):
        self._configure(monkeypatch)

        def boom(*a, **k):
            raise ConnectionError("tarmoq yo'q")

        monkeypatch.setattr(reporter.requests, "post", boom)
        assert reporter.send("salom") is False

    def test_missing_credentials_is_not_a_delivery(self, monkeypatch):
        monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
        assert reporter.send("salom") is False

    def test_one_failed_chunk_makes_the_whole_send_false(self, monkeypatch):
        """Uzun hisobot bo'laklarga bo'linadi. Bittasi yetmasa, xabar
        to'liq yetkazilmagan — "yubordim" deb hisoblash yolg'on bo'lardi."""
        self._configure(monkeypatch)
        calls = []

        def post(*a, **k):
            calls.append(1)
            # Faqat ikkinchi bo'lak rad etiladi
            return self._Resp(ok=len(calls) != 2, status_code=429)

        monkeypatch.setattr(reporter.requests, "post", post)
        text = "\n".join(f"qator {i} " + "x" * 60 for i in range(200))
        assert len(reporter._split(text)) > 2
        assert reporter.send(text) is False
        # Bitta bo'lak yiqilgani qolganlarini to'xtatmasligi kerak
        assert len(calls) == len(reporter._split(text))
