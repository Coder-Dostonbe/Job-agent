"""Vaultga eksport — yon mahsulot, lekin u ham jimgina buzilmasligi kerak.

Bu yerdagi testlarning aksariyati bitta savolga javob beradi: eksport
yiqilganda kunlik hisobot omon qoladimi.
"""
import pathlib

import config
import health
import vault_export


def _vault(tmp_path: pathlib.Path) -> pathlib.Path:
    """Haqiqiy vault tuzilishining minimal nusxasi."""
    (tmp_path / "Raw" / "Sources").mkdir(parents=True)
    return tmp_path


class TestEnabled:
    def test_off_by_default(self):
        assert vault_export.enabled() is False

    def test_disabled_export_writes_nothing_and_stays_invisible(self, vacancy):
        """Vaultsiz ishlatayotgan odam hisobotda "vault" qatorini ko'rmasin."""
        assert vault_export.export([vacancy()], {}, 1, 1) is None
        assert health.summary() == ""


class TestExport:
    def test_writes_a_dated_file(self, tmp_path, monkeypatch, vacancy):
        monkeypatch.setattr(config, "VAULT_PATH", str(_vault(tmp_path)))
        path = vault_export.export([vacancy()], {"python": 3}, 1, 1)
        assert path is not None and path.exists()
        assert path.parent == tmp_path / "Raw" / "Sources"
        assert path.name.startswith("Ish bozori digesti ")

    def test_rerun_updates_instead_of_duplicating(self, tmp_path, monkeypatch, vacancy):
        """Kun ichidagi ikkinchi run ikkinchi fayl yaratmasin."""
        monkeypatch.setattr(config, "VAULT_PATH", str(_vault(tmp_path)))
        vault_export.export([vacancy(title="Birinchi")], {}, 1, 1)
        vault_export.export([vacancy(title="Ikkinchi")], {}, 1, 1)
        files = list((tmp_path / "Raw" / "Sources").iterdir())
        assert len(files) == 1
        assert "Ikkinchi" in files[0].read_text(encoding="utf-8")

    def test_missing_vault_is_reported_not_created(self, tmp_path, monkeypatch, vacancy):
        """Yo'l xato bo'lsa papka yaratilmaydi — fayllar ko'rilmaydigan
        joyga oqib ketishidan ko'ra ogohlantirish afzal."""
        monkeypatch.setattr(config, "VAULT_PATH", str(tmp_path / "yoq"))
        assert vault_export.export([vacancy()], {}, 1, 1) is None
        assert not (tmp_path / "yoq").exists()
        assert any("vault" in a for a in health.alerts())

    def test_write_failure_never_raises(self, tmp_path, monkeypatch, vacancy):
        """Eksport hech qachon kunlik hisobotni o'ldirmasligi kerak."""
        monkeypatch.setattr(config, "VAULT_PATH", str(_vault(tmp_path)))

        def boom(*args, **kwargs):
            raise OSError("disk to'ldi")

        monkeypatch.setattr(pathlib.Path, "write_text", boom)
        assert vault_export.export([vacancy()], {}, 1, 1) is None
        assert any("disk to'ldi" in a for a in health.alerts())


class TestRender:
    def test_frontmatter_matches_the_vault_schema(self, vacancy):
        text = vault_export.render([vacancy()], {}, 1, 1)
        assert text.startswith("---\n")
        for field in ("Title:", "Author:", "Reference:", "ContentType:",
                      "Created:", "Processed: false", "tags:"):
            assert field in text.split("---")[1]
        # Kompilyatsiya qilinmagan manba `false` bo'lib qolishi shart:
        # yozilmagan notani "qayta ishlangan" deb belgilash vaultning
        # eng muhim invariantini buzadi.
        assert "Processed: true" not in text

    def test_wikilinks_in_a_title_cannot_reach_the_vault(self, vacancy):
        """E'lon sarlavhasi vault grafigiga soxta tugun qo'shmasin."""
        text = vault_export.render([vacancy(title="Python [[Junior]] dev")], {}, 1, 1)
        assert "[[" not in text and "]]" not in text
        assert "Junior" in text  # matnning o'zi yo'qolmadi

    def test_hash_in_a_title_does_not_become_a_heading(self, vacancy):
        text = vault_export.render([vacancy(title="C# dasturchi")], {}, 1, 1)
        assert "### 1. C# dasturchi" in text  # qator o'rtasidagi # zararsiz

    def test_ai_analysis_is_written_out(self, vacancy):
        text = vault_export.render([vacancy(ai={
            "score": 82, "verdict": "topshirish_kerak",
            "reason": "Django talab qilinadi", "cv_tip": "Fezot'ni yuqoriga",
        })], {}, 1, 1)
        assert "AI ball: 82/100 (topshirish kerak)" in text
        assert "AI izohi: Django talab qilinadi" in text
        assert "CV maslahati: Fezot'ni yuqoriga" in text

    def test_broken_ai_falls_back_to_the_keyword_score(self, vacancy):
        """Hisobotdagi qoida bu yerda ham amal qiladi: ballsiz "tahlil"
        AI bahosi bo'lib ko'rinmasin."""
        text = vault_export.render([vacancy(score=55, ai={"verdict": "x"})], {}, 1, 1)
        assert "AI ball" not in text
        assert "Keyword ball: 55" in text

    def test_missing_description_is_flagged(self, vacancy):
        text = vault_export.render([vacancy(text="")], {}, 1, 1)
        assert "Tavsif yuklanmadi" in text

    def test_low_scores_are_written_in_full(self, vacancy):
        """Telegram'dagi REPORT_LOW_LIMIT qisqartmasi faylda kerak emas."""
        low = [vacancy(url=f"https://example.test/{i}", title=f"E'lon {i}")
               for i in range(config.REPORT_LOW_LIMIT + 10)]
        text = vault_export.render([], {}, 40, 0, low=low)
        assert text.count("https://example.test/") == len(low)

    def test_health_problems_are_recorded(self, vacancy):
        health.expect("hh.uz")
        health.error("hh.uz", "ConnectionError")
        text = vault_export.render([vacancy()], {}, 1, 1)
        assert "Manbalar holati" in text
        assert "hh.uz" in text

    def test_empty_day_still_produces_a_valid_note(self):
        text = vault_export.render([], {}, 0, 0)
        assert text.startswith("---\n")
        assert "Yangi e'lonlar: 0 ta" in text
