"""Faqat dasturlash vakansiyalari o'tsin — va tavsif to'g'ri tanlansin.

Ikki muammo bir ildizdan: hisobotda joy cheklangan, shuning uchun kerakmas
e'lon o'tib ketsa yoki kerakli e'lon ma'lumotsiz qolsa, natija bir xil —
chinakam vakansiya ko'rinmaydi.
"""
import pytest

import config
import main
from collectors import hh
from scoring import vacancy_filter


class TestRoleCheck:
    @pytest.mark.parametrize("title", [
        "Продукт-менеджер (SaaS платформа для транспорта)",
        "Директор департамента собственной разработки (Ташкент, офис)",
        "Менеджер отдела B2B-продаж (IT / SaaS)",
    ])
    def test_the_reported_examples_are_rejected(self, title):
        """User bevosita ko'rsatgan uchta e'lon — hisobotga tushmasin."""
        assert vacancy_filter.role_check(title)

    @pytest.mark.parametrize("title", [
        "Python-разработчик",
        "Django Developer (Middle)",
        "Backend разработчик (Python)",
        "Junior Python dasturchi",
        "Разработчик на Python/Django",
        "AI-разработчик (вайбкодер)",
        "Программист Python",
    ])
    def test_real_developer_roles_survive(self, title):
        """Eng muhim test: filtr keraklisini yeb qo'ymasin. Bitta noto'g'ri
        rad etish — butunlay yo'qolgan vakansiya, uni hech kim sezmaydi."""
        assert vacancy_filter.role_check(title) == ""

    @pytest.mark.parametrize("title,expected", [
        ("Руководитель отдела разработки", "руководител"),
        ("Head of Engineering", "head of"),
        ("Project Manager (IT)", "project manager"),
        ("UX/UI дизайнер", "дизайнер"),
        ("Бизнес-аналитик", "бизнес-аналитик"),
        ("Менеджер по продажам", "продаж"),
        ("HR-менеджер", "hr-менеджер"),
        ("Системный администратор", "системный администратор"),
        ("Оператор call-центра", "оператор"),
    ])
    def test_it_names_the_matched_term(self, title, expected):
        """Sabab qaytariladi — jimgina filtr eng yomon filtr."""
        assert vacancy_filter.role_check(title) == expected

    def test_the_body_is_not_searched(self):
        """Haqiqiy dasturchi e'lonining matnida "отдел продаж" va "менеджер
        проекта" muntazam uchraydi — kim bilan ishlashi tasvirlanadi. Shuning
        uchun faqat sarlavha tekshiriladi."""
        body = "Вы будете работать с отделом продаж и менеджером проекта, " \
               "подчиняться директору по технологиям."
        assert vacancy_filter.role_check(body) != ""   # sarlavha bo'lsa rad etilardi
        # ...lekin pipeline uni faqat sarlavhaga qo'llaydi:
        assert vacancy_filter.role_check("Python-разработчик") == ""

    def test_case_does_not_matter(self):
        assert vacancy_filter.role_check("ПРОДУКТ-МЕНЕДЖЕР")


class TestPipelineRejection:
    def test_hh_vacancies_are_not_exempt(self, monkeypatch, vacancy):
        """hh.uz turdagi filtrdan ozod, chunki u faqat vakansiya qaytaradi.
        Lekin aynan hh.uz shu rollarni eng ko'p olib keladi — rol tekshiruvi
        undan ham o'tishi kerak."""
        kept = _run_pipeline(monkeypatch, [
            vacancy(url="https://hh.uz/1", title="Продукт-менеджер (SaaS)"),
            vacancy(url="https://hh.uz/2", title="Python-разработчик"),
        ])
        assert [v["title"] for v in kept] == ["Python-разработчик"]

    def test_telegram_posts_are_checked_too(self, monkeypatch, vacancy):
        kept = _run_pipeline(monkeypatch, [
            vacancy(url="https://t.me/c/1", source="t.me/kanal",
                    title="Менеджер отдела B2B-продаж", text="вакансия, зарплата"),
            vacancy(url="https://t.me/c/2", source="t.me/kanal",
                    title="Python dasturchi kerak", text="vakansiya, oylik"),
        ])
        assert [v["title"] for v in kept] == ["Python dasturchi kerak"]


def _run_pipeline(monkeypatch, vacancies):
    """main.run() ni soxta kollektorlar bilan ishlatib, hisobotga tushganini
    qaytaradi."""
    import asyncio
    import reporter
    from collectors import olx, tg_channels

    shown = []
    monkeypatch.setattr(hh, "collect", lambda: list(vacancies))
    monkeypatch.setattr(olx, "collect", lambda: [])

    async def no_tg():
        return []

    monkeypatch.setattr(tg_channels, "collect", no_tg)
    monkeypatch.setattr(reporter, "send", lambda text: True)
    monkeypatch.setattr(reporter, "build_report",
                        lambda s, *a, **k: shown.extend(s) or "hisobot")
    asyncio.run(main.run())
    return shown


class TestDescriptionPriority:
    """F: tavsif qaysi vakansiyalarga yuklanishi tanlovni belgilaydi."""

    def test_the_most_promising_titles_come_first(self, vacancy):
        weak = vacancy(title="Разработчик", text="")
        strong = vacancy(title="Python Django backend разработчик", text="")
        assert hh._priority(strong) < hh._priority(weak)

    def test_rejected_roles_sink_to_the_bottom(self, vacancy):
        """Menejer e'loniga so'rov sarflash ortiqcha — u baribir rad etiladi."""
        manager = vacancy(title="Директор департамента разработки", text="")
        weakest_dev = vacancy(title="Стажер", text="")
        assert hh._priority(weakest_dev) < hh._priority(manager)

    def test_the_limit_takes_the_best_not_the_first(self, monkeypatch, vacancy):
        """Asosiy tuzatish: ilgari birinchi N tasi olinardi, ya'ni ro'yxat
        oxiridagi a'lo vakansiya faqat tartib sababli ma'lumotsiz qolardi."""
        monkeypatch.setattr(config, "HH_DESC_LIMIT", 2)
        asked = []
        monkeypatch.setattr(hh, "_description",
                            lambda url: asked.append(url) or "matn")
        monkeypatch.setattr(hh, "_report_description_health",
                            lambda *a, **k: None)

        items = [vacancy(url=f"https://hh.uz/{i}", title="Менеджер по продажам")
                 for i in range(5)]
        items.append(vacancy(url="https://hh.uz/gold",
                             title="Python Django backend разработчик"))
        hh._fill_descriptions(items)

        assert "https://hh.uz/gold" in asked
        assert len(asked) == 2
