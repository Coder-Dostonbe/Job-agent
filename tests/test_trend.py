"""Keskin pasayish: nol emas, lekin odatdagidan ancha kam.

Bu yerdagi eng muhim testlar ogohlantirish **chiqmasligi** kerak bo'lgan
holatlar haqida. Noto'g'ri ogohlantirish diagnostikani foydasiz qiladi:
har kuni "muammo bor" yozuvini ko'rgan odam uni o'qishni to'xtatadi va
haqiqiy nosozlikni ham o'tkazib yuboradi.
"""
import config
import health
import storage
import trend


class TestMedian:
    def test_odd_length(self):
        assert trend._median([1, 100, 5]) == 5

    def test_even_length(self):
        assert trend._median([10, 20, 30, 40]) == 25

    def test_one_bad_day_does_not_move_it(self):
        """Nega o'rtacha emas: bitta yiqilgan kun o'rtachani 54 dan 46 ga
        tushiradi va ertasiga haqiqiy pasayish sezilmay qoladi."""
        assert trend._median([63, 60, 0, 58, 61]) == 60


class TestCheck:
    def test_a_sharp_drop_is_caught(self):
        """Asosiy holat: sahifa qisman o'zgargan, kollektor yiqilmagan."""
        found = trend.check({"hh.uz": [63, 60, 58, 61]}, {"hh.uz": 6})
        assert len(found) == 1
        source, message = found[0]
        assert source == "hh.uz"
        assert "6 ta" in message and "60" in message

    def test_a_normal_day_is_quiet(self):
        assert trend.check({"hh.uz": [63, 60, 58, 61]}, {"hh.uz": 57}) == []

    def test_growth_is_quiet(self):
        assert trend.check({"hh.uz": [63, 60, 58, 61]}, {"hh.uz": 120}) == []

    def test_exactly_at_the_threshold_is_quiet(self):
        """Chegara — 50%. Aynan 30 (medianasi 60) ogohlantirmasligi kerak,
        aks holda oddiy tebranish ham xabar berib turadi."""
        assert trend.check({"hh.uz": [60, 60, 60]}, {"hh.uz": 30}) == []
        assert len(trend.check({"hh.uz": [60, 60, 60]}, {"hh.uz": 29})) == 1

    def test_short_history_is_not_compared(self):
        """Birinchi kunlar: taqqoslash uchun chiziq yo'q."""
        assert trend.check({"hh.uz": [63, 60]}, {"hh.uz": 2}) == []

    def test_unknown_source_is_ignored(self):
        assert trend.check({}, {"yangi-manba": 1}) == []

    def test_small_sources_do_not_cry_wolf(self):
        """Odatda 4 ta beradigan Telegram bugun 1 ta berdi — bu normal
        tebranish, nosozlik emas."""
        assert trend.check({"telegram": [4, 3, 5, 4]}, {"telegram": 1}) == []

    def test_a_big_source_dropping_to_zero_is_caught(self):
        found = trend.check({"olx.uz": [41, 38, 40]}, {"olx.uz": 0})
        assert len(found) == 1

    def test_each_source_is_judged_separately(self):
        found = trend.check(
            {"hh.uz": [63, 60, 58], "olx.uz": [41, 38, 40]},
            {"hh.uz": 61, "olx.uz": 3},
        )
        assert [s for s, _ in found] == ["olx.uz"]


class TestHealthIntegration:
    """Ogohlantirish hisobotga chiqishi kerak — aks holda mantiq behuda."""

    def test_a_drop_shows_up_in_the_report_line(self):
        health.expect("hh.uz")
        health.found("hh.uz", 6)
        health.warn("hh.uz", "odatdagidan keskin kam: 6 ta")
        assert health._entry("hh.uz").status == "degraded"
        assert len(health.alerts()) == 1
        assert "keskin kam" in health.alerts()[0]

    def test_a_warning_does_not_look_like_an_error(self):
        """Xato emas — "1 ta xato" matni chiqmasligi kerak."""
        health.expect("hh.uz")
        health.found("hh.uz", 6)
        health.warn("hh.uz", "odatdagidan keskin kam: 6 ta")
        assert "xato" not in health.alerts()[0]

    def test_an_error_and_a_warning_both_show(self):
        health.expect("hh.uz")
        health.found("hh.uz", 6)
        health.error("hh.uz", "tavsif yuklanmadi")
        health.warn("hh.uz", "odatdagidan keskin kam: 6 ta")
        alerts = health.alerts()
        assert len(alerts) == 2

    def test_healthy_sources_stay_silent(self):
        health.expect("hh.uz")
        health.found("hh.uz", 63)
        assert health.alerts() == []


class TestStorageRoundTrip:
    def test_counts_survive_to_the_next_run(self):
        storage.record_counts({"hh.uz": 63, "olx.uz": 41})
        storage.record_counts({"hh.uz": 60, "olx.uz": 38})
        history = storage.recent_counts(7)
        assert sorted(history["hh.uz"]) == [60, 63]
        assert sorted(history["olx.uz"]) == [38, 41]

    def test_the_window_is_limited(self):
        for n in range(10):
            storage.record_counts({"hh.uz": n})
        assert len(storage.recent_counts(7)["hh.uz"]) == 7

    def test_the_newest_runs_are_the_ones_kept(self, monkeypatch):
        """Oyna eng oxirgi run'lardan olinishi kerak, tasodifiy 7 tadan emas."""
        class FakeClock:
            n = 0

            @classmethod
            def now(cls):
                cls.n += 1
                return _Stamp(cls.n)

        class _Stamp:
            def __init__(self, n):
                self.n = n

            def isoformat(self):
                return f"2026-08-{self.n:02d}T09:00:00"

        monkeypatch.setattr(storage, "datetime", FakeClock)
        for n in range(1, 11):
            storage.record_counts({"hh.uz": n * 10})
        assert storage.recent_counts(3)["hh.uz"] == [100, 90, 80]

    def test_no_history_is_not_an_error(self):
        assert storage.recent_counts(7) == {}

    def test_empty_counts_write_nothing(self):
        storage.record_counts({})
        assert storage.recent_counts(7) == {}

    def test_a_broken_database_does_not_stop_the_run(self, monkeypatch):
        """Tarix yozilmasa trend ishlamaydi — lekin hisobot baribir ketishi
        kerak. Ombor nosozligi haqida `storage` o'zi ogohlantiradi."""
        def boom(*a, **k):
            raise RuntimeError("baza yiqildi")

        monkeypatch.setattr(storage, "_connect", boom)
        storage.record_counts({"hh.uz": 63})  # istisno ko'tarilmasligi kerak
        assert storage.recent_counts(7) == {}


class TestCheckAndRecord:
    def test_the_baseline_does_not_include_today(self):
        """Bugungi son o'z chizig'iga kirsa, pasayish o'zini oqlab qo'yadi."""
        for _ in range(4):
            storage.record_counts({"hh.uz": 60})
        health.expect("hh.uz")
        health.found("hh.uz", 6)
        trend.check_and_record()
        assert len(health.alerts()) == 1
        # Yozildi ham: ertaga bu son tarixda bo'lishi kerak
        assert 6 in storage.recent_counts(7)["hh.uz"]

    def test_today_is_compared_before_it_is_written(self):
        """Tartib: avval taqqoslash, keyin yozish. Teskarisi bo'lsa bugungi
        son o'z bazaviy chizig'iga kirib, tarix yetarli emasligini yashirardi."""
        for _ in range(config.TREND_MIN_RUNS - 1):
            storage.record_counts({"hh.uz": 60})
        health.expect("hh.uz")
        health.found("hh.uz", 6)
        trend.check_and_record()
        assert health.alerts() == []  # tarix hali yetarli emas

    def test_skipped_sources_are_not_recorded(self, monkeypatch):
        """Telegram sozlanmagan bo'lsa 0 yozish chiziqni nolga tushiradi va
        keyinchalik haqiqiy pasayish sezilmay qoladi."""
        health.expect("telegram")
        health.skipped("telegram", "TG_API_ID yo'q")
        trend.check_and_record()
        assert "telegram" not in storage.recent_counts(7)

    def test_countless_components_are_not_recorded(self):
        """Ombor e'lon qaytarmaydi — uni sonlar bilan taqqoslash ma'nosiz."""
        health.alive("storage", "postgres")
        trend.check_and_record()
        assert "storage" not in storage.recent_counts(7)

    def test_an_already_failing_source_is_not_warned_twice(self):
        """0 ta natija haqida `health` allaqachon gapirgan — trend ustiga
        ikkinchi qatorni qo'shmasligi kerak."""
        for _ in range(4):
            storage.record_counts({"hh.uz": 60})
        health.expect("hh.uz")  # scanned = 0, ya'ni "empty"
        trend.check_and_record()
        assert len(health.alerts()) == 1
        assert "keskin kam" not in health.alerts()[0]

    def test_the_zero_is_still_recorded(self):
        """Ogohlantirmasak ham, yiqilgan kun tarixda qolishi kerak —
        median uni ko'tara oladi, yashirish esa chiziqni buzadi."""
        health.expect("hh.uz")
        trend.check_and_record()
        assert storage.recent_counts(7)["hh.uz"] == [0]

    def test_nothing_collected_at_all_is_harmless(self):
        trend.check_and_record()
        assert health.alerts() == []

    def test_a_lasting_drop_becomes_the_new_normal_after_four_warnings(self):
        """Usulning ochiq cheklovi, yashirilmasin: past qiymatlar oynani
        egallagach median ularga ko'chadi va ogohlantirish o'chadi. Bu
        7 run'lik oynada 4 ta xabardan keyin sodir bo'ladi — raqam shu yerda
        mahkamlangan, chunki `TREND_HISTORY_RUNS` o'zgarsa u ham o'zgaradi."""
        def one_run(count):
            health.reset()
            health.expect("hh.uz")
            health.found("hh.uz", count)
            trend.check_and_record()
            return bool(health.alerts())

        for _ in range(config.TREND_HISTORY_RUNS):
            one_run(60)
        warned = [one_run(6) for _ in range(6)]
        assert warned == [True, True, True, True, False, False]
