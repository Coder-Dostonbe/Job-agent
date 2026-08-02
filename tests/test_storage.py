"""Ombor: Postgres yiqilishi jimgina o'tib ketmasin."""
import sqlite3

import pytest

import config
import health
import storage


@pytest.fixture
def broken_pg(monkeypatch):
    """DATABASE_URL bor, lekin Postgres ishlamaydi."""
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    monkeypatch.setattr(storage, "_connect_pg", lambda: (_ for _ in ()).throw(
        OSError("connection refused")))
    storage.reset_state()


@pytest.fixture
def on_actions(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")


def test_local_sqlite_is_not_a_problem(vacancy):
    """DATABASE_URL yo'q + lokal mashina = normal ish rejimi."""
    storage.filter_new([vacancy()])
    assert health.alerts() == []
    assert "storage sqlite ✅" in health.summary()


def test_missing_url_on_actions_is_a_problem(vacancy, on_actions):
    """Runner diski har run'dan keyin o'chadi: tarix hech qachon saqlanmaydi
    va har kuni o'sha vakansiyalar qayta keladi. Ilgari bu umuman sezilmasdi."""
    storage.reset_state()
    storage.filter_new([vacancy()])
    assert len(health.alerts()) == 1
    assert "DATABASE_URL" in health.alerts()[0]


def test_read_fallback_warns_about_repeats(vacancy, broken_pg):
    storage.filter_new([vacancy()])
    assert "takror" in health.alerts()[0]
    assert "sqlite (zaxira)" in health.summary()


def test_write_fallback_warns_about_lost_history(vacancy, broken_pg):
    storage.save([vacancy()])
    assert "tarixga yozilmadi" in health.alerts()[0]


def test_fallback_on_actions_mentions_the_wiped_disk(vacancy, broken_pg, on_actions):
    storage.filter_new([vacancy()])
    assert "run tugashi bilan o'chadi" in health.alerts()[0]


def test_warning_is_not_repeated_per_connection(vacancy, broken_pg):
    """Bir run'da _db() bir necha marta ochiladi — ogohlantirish bittada qolsin."""
    storage.filter_new([vacancy()])
    storage.save([vacancy()])
    storage.filter_new([vacancy()])
    assert len(health.alerts()) == 1


def test_failed_save_does_not_kill_the_report(vacancy, monkeypatch):
    """Tayyor vakansiyalarni yo'qotgandan ko'ra ertaga takrorlangani afzal."""
    def boom(op="read"):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(storage, "_db", boom)
    storage.save([vacancy()])  # istisno chiqmasligi kerak
    assert len(health.alerts()) == 1
    assert "0 ta natija" not in health.alerts()[0]  # kollektor matni emas


class TestRetry:
    """Serverless baza sovuq holatdan uyg'onishi bir necha soniya oladi —
    bitta timeout uchun butun tarixdan voz kechish juda qimmat."""

    @pytest.fixture
    def flaky_psycopg(self, monkeypatch):
        class FakeCursor:
            def execute(self, *a):
                pass

            def fetchall(self):
                return []

            def executemany(self, *a):
                pass

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def commit(self):
                pass

            def close(self):
                pass

        class FakePsycopg:
            def __init__(self, fail_times):
                self.fail_times = fail_times
                self.calls = 0

            def connect(self, *a, **kw):
                self.calls += 1
                if self.calls <= self.fail_times:
                    raise OSError("temporary network blip")
                return FakeConn()

        def install(fail_times):
            fake = FakePsycopg(fail_times)
            monkeypatch.setitem(__import__("sys").modules, "psycopg", fake)
            monkeypatch.setattr(config, "DATABASE_URL", "postgresql://x")
            monkeypatch.setattr(config, "DB_RETRY_DELAY", 0)
            storage.reset_state()
            return fake

        return install

    def test_transient_failure_recovers(self, vacancy, flaky_psycopg):
        fake = flaky_psycopg(fail_times=1)
        storage.filter_new([vacancy()])
        assert fake.calls == 2
        assert health.alerts() == []
        assert "storage postgres ✅" in health.summary()

    def test_persistent_failure_falls_back(self, vacancy, flaky_psycopg):
        fake = flaky_psycopg(fail_times=99)
        storage.filter_new([vacancy()])
        assert fake.calls == config.DB_CONNECT_RETRIES
        assert len(health.alerts()) == 1

    def test_no_retry_storm_after_giving_up(self, vacancy, flaky_psycopg):
        """Bir marta taslim bo'lgach, shu run'da qayta urinilmaydi — aks holda
        har chaqiruvda yana kutib, run'ni cho'zib yuborardi."""
        fake = flaky_psycopg(fail_times=99)
        storage.filter_new([vacancy()])
        storage.save([vacancy()])
        assert fake.calls == config.DB_CONNECT_RETRIES


class TestDedup:
    def test_url_dedup_within_one_run(self, vacancy):
        same = [vacancy(), vacancy()]
        assert len(storage.filter_new(same)) == 1

    def test_saved_vacancy_is_not_new_next_time(self, vacancy):
        v = vacancy()
        storage.save([v])
        assert storage.filter_new([v]) == []

    def test_title_dedup_for_configured_sources(self, vacancy, monkeypatch):
        """OLX'da qayta joylangan e'lon yangi URL oladi — URL dedupi uni
        ushlamaydi, shuning uchun sarlavha ham tekshiriladi."""
        monkeypatch.setattr(config, "TITLE_DEDUP_SOURCES", {"olx.uz"})
        first = vacancy(source="olx.uz", url="https://olx/1", title="Python dasturchi!!!")
        storage.save([first])
        again = vacancy(source="olx.uz", url="https://olx/2", title="python  dasturchi")
        assert storage.filter_new([again]) == []

    def test_empty_url_is_skipped(self, vacancy):
        assert storage.filter_new([vacancy(url="")]) == []
