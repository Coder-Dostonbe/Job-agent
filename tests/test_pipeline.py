"""Run darajasidagi himoya: agent jimgina o'lib qolmasin.

Va hh.uz tavsiflarining sekin degradatsiyasi — har bir so'rov muvaffaqiyatli
bo'lsa ham, selector o'zgargan bo'lsa matn bo'sh keladi va vakansiya deyarli
ballanmaydi.
"""
import pytest

import config
import health
import main
import reporter
import storage
from collectors import hh, olx, tg_channels


class TestDescriptionDegradation:
    def test_everything_loaded_is_quiet(self):
        health.expect("hh.uz")
        health.found("hh.uz", 63)
        hh._report_description_health(25, 25, aborted=False)
        assert health.alerts() == []

    def test_scattered_failures_are_caught(self):
        """25 tadan 12 tasi — hech qanday so'rov yiqilmagan, lekin hisobot
        sifati yarmiga tushgan. Ilgari bu umuman sezilmasdi."""
        health.expect("hh.uz")
        health.found("hh.uz", 63)
        hh._report_description_health(25, 12, aborted=False)
        assert len(health.alerts()) == 1
        assert health._entry("hh.uz").status == "degraded"

    def test_changed_selector_gives_empty_texts(self):
        health.expect("hh.uz")
        health.found("hh.uz", 63)
        hh._report_description_health(25, 0, aborted=False)
        assert len(health.alerts()) == 1

    def test_threshold_is_inclusive(self):
        health.expect("hh.uz")
        health.found("hh.uz", 63)
        hh._report_description_health(10, 7, aborted=False)  # aynan 0.7
        assert health.alerts() == []

    def test_aborted_run_says_so(self):
        health.expect("hh.uz")
        health.found("hh.uz", 63)
        hh._report_description_health(25, 4, aborted=True)
        assert "to'xtatildi" in health.alerts()[0]

    def test_no_vacancies_means_no_division_by_zero(self):
        health.expect("hh.uz")
        health.found("hh.uz", 0)
        hh._report_description_health(0, 0, aborted=False)
        assert len(health.alerts()) == 1  # faqat "empty", tavsif haqida emas


class TestCrashGuard:
    @pytest.fixture
    def failing_run(self, monkeypatch):
        async def boom():
            raise RuntimeError("sinov uchun ataylab yiqilish")

        monkeypatch.setattr(main, "run", boom)

    @pytest.fixture
    def outbox(self, monkeypatch):
        sent = []
        monkeypatch.setattr(reporter, "send", lambda text: sent.append(text))
        return sent

    def test_crash_is_reported_then_re_raised(self, failing_run, outbox):
        """Qayta ko'tarish shart: Actions run'i ham qizil bo'lsin, aks holda
        yashil belgi hamma narsa joyida degan yolg'on taassurot beradi."""
        with pytest.raises(RuntimeError):
            main.main()
        assert len(outbox) == 1
        assert outbox[0].startswith("🚨")

    def test_a_broken_messenger_does_not_hide_the_original_error(
            self, failing_run, monkeypatch):
        def broken_send(text):
            raise ConnectionError("Telegram ham yiqildi")

        monkeypatch.setattr(reporter, "send", broken_send)
        with pytest.raises(RuntimeError):
            main.main()


class TestNoVacanciesReport:
    def test_it_carries_the_diagnostics(self):
        """Diagnostikasiz bu xabar ikki xil holatni bir xil ko'rsatardi:
        haqiqatan ish yo'q va scraper sinib qolgan."""
        health.expect("hh.uz")
        health.error("hh.uz", "timeout")
        text = main._no_vacancies_report()
        assert "Bugun yangi mos vakansiya topilmadi" in text
        assert "hh.uz" in text

    def test_it_stays_short_when_everything_is_fine(self):
        health.expect("hh.uz")
        health.found("hh.uz", 63)
        assert "Manbalarda muammo" not in main._no_vacancies_report()


class TestCrashMarker:
    """Bitta yiqilish — bitta xabar.

    Agent yiqilganda xabarni ikki joy yubora oladi: Python (main.py) va
    Actions workflow'idagi zaxira bosqich. Belgi fayli ularni ajratadi —
    aks holda foydalanuvchi bitta nosozlik uchun ikkita xabar olardi, yoki
    (belgi juda erta qo'yilsa) umuman hech narsa olmasdi.
    """

    @pytest.fixture(autouse=True)
    def marker(self, monkeypatch, tmp_path):
        path = tmp_path / ".crash-notified"
        monkeypatch.setattr(main, "CRASH_MARKER", str(path))
        return path

    @pytest.fixture
    def failing_run(self, monkeypatch):
        async def boom():
            raise RuntimeError("sinov uchun ataylab yiqilish")

        monkeypatch.setattr(main, "run", boom)

    def test_delivered_report_leaves_the_marker(self, failing_run, marker, monkeypatch):
        monkeypatch.setattr(reporter, "send", lambda text: True)
        with pytest.raises(RuntimeError):
            main.main()
        assert marker.exists()

    def test_undelivered_report_leaves_no_marker(self, failing_run, marker, monkeypatch):
        """Telegram rad etgan bo'lsa zaxira bildirishnoma ishlashi shart —
        shuning uchun belgi qo'yilmaydi."""
        monkeypatch.setattr(reporter, "send", lambda text: False)
        with pytest.raises(RuntimeError):
            main.main()
        assert not marker.exists()

    def test_broken_messenger_leaves_no_marker(self, failing_run, marker, monkeypatch):
        def broken_send(text):
            raise ConnectionError("Telegram ham yiqildi")

        monkeypatch.setattr(reporter, "send", broken_send)
        with pytest.raises(RuntimeError):
            main.main()
        assert not marker.exists()

    def test_unwritable_marker_does_not_hide_the_original_error(
            self, failing_run, monkeypatch, tmp_path):
        """Belgi yozilmasa eng yomoni takroriy xabar keladi — asl istisno
        baribir ko'tarilishi kerak."""
        monkeypatch.setattr(main, "CRASH_MARKER", str(tmp_path / "yoq" / "belgi"))
        monkeypatch.setattr(reporter, "send", lambda text: True)
        with pytest.raises(RuntimeError):
            main.main()

    def test_a_healthy_run_leaves_no_marker(self, marker, monkeypatch):
        async def fine():
            return None

        monkeypatch.setattr(main, "run", fine)
        main.main()
        assert not marker.exists()


class TestDelivery:
    """Yetkazilmagan hisobot jimgina yo'qolmasligi kerak.

    Eng qimmat nosozlik shu edi: Telegram xabarni rad etadi, agent esa
    vakansiyalarni "ko'rilgan" deb yozib, "Hisobot yuborildi ✅" deb
    log qoldirib, yashil tugaydi. O'sha vakansiyalar boshqa hech qachon
    ko'rsatilmaydi va buni bilishning yo'li yo'q.
    """

    def test_a_rejected_report_fails_the_run(self, monkeypatch):
        monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")
        monkeypatch.setattr(reporter, "send", lambda text: False)
        with pytest.raises(RuntimeError):
            main._deliver("hisobot")

    def test_a_delivered_report_is_quiet(self, monkeypatch):
        monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")
        monkeypatch.setattr(reporter, "send", lambda text: True)
        main._deliver("hisobot")  # istisno bo'lmasligi kerak

    def test_an_unconfigured_telegram_is_not_a_failure(self, monkeypatch):
        """Lokal ishlashda token yo'q — hisobot konsolga chiqadi va bu
        normal. Aks holda har bir lokal run xato bilan tugardi."""
        monkeypatch.setattr(reporter, "send", lambda text: False)
        main._deliver("hisobot")  # config bo'sh (conftest), istisno yo'q

    def test_vacancies_are_not_marked_seen_when_delivery_fails(
            self, monkeypatch, vacancy):
        """Asosiy zarar shu yerda: saqlash yuborishdan oldin bo'lsa,
        yetkazilmagan hisobotdagi vakansiyalar butunlay yo'qoladi."""
        monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")
        monkeypatch.setattr(reporter, "send", lambda text: False)
        monkeypatch.setattr(hh, "collect", lambda: [vacancy(score=80)])
        monkeypatch.setattr(olx, "collect", lambda: [])

        async def no_tg():
            return []

        monkeypatch.setattr(tg_channels, "collect", no_tg)

        with pytest.raises(RuntimeError):
            main.main()
        # Ertaga qayta ko'rsatilishi uchun tarixda bo'lmasligi kerak
        assert storage.filter_new([vacancy(score=80)]) != []

    def test_vacancies_are_marked_seen_once_delivered(self, monkeypatch, vacancy):
        monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")
        monkeypatch.setattr(reporter, "send", lambda text: True)
        monkeypatch.setattr(hh, "collect", lambda: [vacancy(score=80)])
        monkeypatch.setattr(olx, "collect", lambda: [])

        async def no_tg():
            return []

        monkeypatch.setattr(tg_channels, "collect", no_tg)

        main.main()
        assert storage.filter_new([vacancy(score=80)]) == []
