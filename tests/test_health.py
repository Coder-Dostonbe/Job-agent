"""Manba holatlari — "scraper sindi" ni "bugun ish yo'q" dan ajratish."""
import health


def test_normal_source_is_ok():
    health.expect("hh.uz")
    health.found("hh.uz", 63)
    assert health._entry("hh.uz").status == "ok"
    assert health.alerts() == []


def test_zero_results_without_error_is_suspicious():
    """Eng muhim holat: so'rov o'tdi, xato yo'q, natija ham yo'q.
    Odatda bu selector yoki sayt tuzilmasi o'zgargani."""
    health.expect("hh.uz")
    health.found("hh.uz", 0)
    assert health._entry("hh.uz").status == "empty"
    assert len(health.alerts()) == 1


def test_read_but_nothing_matched_is_not_an_alert():
    """Telegram kanallari o'qildi, lekin kalit so'zlarga mos post yo'q —
    bu normal holat, ogohlantirish emas."""
    health.expect("telegram")
    health.found("telegram", kept=0, scanned=40)
    assert health._entry("telegram").status == "filtered"
    assert health.alerts() == []


def test_partial_failure_is_degraded():
    health.expect("telegram")
    health.found("telegram", kept=6, scanned=40)
    health.error("telegram", "@deadchannel: mavjud emas")
    assert health._entry("telegram").status == "degraded"
    assert "deadchannel" in health.alerts()[0]


def test_total_failure():
    health.expect("olx.uz")
    health.error("olx.uz", "timeout")
    assert health._entry("olx.uz").status == "failed"
    assert health.alerts()[0].startswith("❌")


def test_skipped_source_is_reported():
    health.expect("telegram")
    health.skipped("telegram", "session yo'q")
    assert health._entry("telegram").status == "skipped"
    assert "session yo'q" in health.alerts()[0]


def test_expect_without_result_still_shows_up():
    """Kollektor hech narsa yozib ulgurmay yiqilsa ham hisobotda ko'rinsin —
    yo'q manba sezilmaydigan manba."""
    health.expect("hh.uz")
    assert "hh.uz" in health.summary()


def test_summary_lists_every_source():
    health.expect("hh.uz")
    health.found("hh.uz", 63)
    health.expect("telegram")
    health.skipped("telegram", "session yo'q")
    summary = health.summary()
    assert "hh.uz 63 ✅" in summary
    assert "telegram 0 ⏭" in summary


def test_empty_registry_gives_empty_summary():
    assert health.summary() == ""


class TestCountlessComponents:
    """`alive()` — ombor va AI kabi "nechta e'lon qaytardi" savoliga javob
    bermaydigan komponentlar uchun."""

    def test_alive_counts_as_ok(self):
        health.alive("storage", "postgres")
        assert health._entry("storage").status == "ok"
        assert health.alerts() == []

    def test_detail_replaces_the_count(self):
        health.alive("storage", "postgres")
        assert "storage postgres ✅" in health.summary()

    def test_alive_with_error_is_degraded_not_failed(self):
        health.alive("storage", "sqlite")
        health.error("storage", "Postgres ishlamadi")
        assert health._entry("storage").status == "degraded"

    def test_alert_omits_the_collector_wording(self):
        """Sanoqsiz komponent uchun "N ta topildi" ma'nosiz."""
        health.alive("storage", "sqlite")
        health.error("storage", "Postgres ishlamadi")
        alert = health.alerts()[0]
        assert "ta topildi" not in alert
        assert "Postgres ishlamadi" in alert
