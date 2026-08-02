"""hh.uz dan vakansiyalarni yig'ish.

Rasmiy API (api.hh.uz) endi ish izlovchilar uchun yopiq: /vacancies
avtorizatsiyasiz 403 qaytaradi, ilova ro'yxatdan o'tkazish esa faqat
ish beruvchilarga ochiq (hh 2025-yil 15-dekabrda soiskatel API'sini
to'xtatgan). Shuning uchun oddiy qidiruv sahifasidan o'qiymiz.

Sahifa ichida to'liq JSON holat bor (<template id="HH-Lux-InitialState">),
shuning uchun HTML tuzilishiga bog'lanib qolmaymiz — undan tayyor
ma'lumotni olamiz. Qisqacha tavsif JSON'da yo'q, shuning uchun eng mos
vakansiyalarning to'liq matni alohida yuklanadi.
"""
import html
import json
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

import config
import health

log = logging.getLogger("hh")

SOURCE = "hh.uz"
SEARCH_URL = "https://hh.uz/search/vacancy"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en;q=0.9",
}

# Bitta sessiya — cookie'lar saqlanadi. Cookie'siz va tez ketma-ket so'rovlarda
# hh.uz ikkinchi so'rovdanoq 403 qaytaradi (GitHub Actions IP'sida shunday bo'ldi).
_session = requests.Session()
_session.headers.update(HEADERS)


def _get(url: str, **kwargs) -> requests.Response:
    """Sekinlashtirilgan so'rov — hh.uz bot himoyasiga tushmaslik uchun."""
    time.sleep(config.HH_REQUEST_DELAY)
    resp = _session.get(url, timeout=20, **kwargs)
    resp.raise_for_status()
    return resp
STATE_RE = re.compile(
    r'<template[^>]*id="HH-Lux-InitialState"[^>]*>(.*?)</template>', re.S
)
EXPERIENCE_UZ = {
    "noExperience": "tajriba talab qilinmaydi",
    "between1And3": "1-3 yil",
    "between3And6": "3-6 yil",
    "moreThan6": "6 yildan ortiq",
}


def _state(text: str) -> dict:
    """Sahifaga singdirilgan JSON holatni ajratib oladi."""
    m = STATE_RE.search(text)
    if not m:
        raise ValueError("HH-Lux-InitialState topilmadi (sahifa o'zgargan?)")
    return json.loads(html.unescape(m.group(1)))


def _salary(comp: dict) -> str:
    if not comp or "noCompensation" in comp:
        return ""
    frm, to = comp.get("from"), comp.get("to")
    cur = comp.get("currencyCode", "")
    if frm and to and frm != to:
        amount = f"{frm}–{to}"
    else:
        amount = str(frm or to or "")
    return f"{amount} {cur}".strip() if amount else ""


def _clean(v: dict) -> dict:
    company = v.get("company") or {}
    return {
        "source": "hh.uz",
        # displayHost mintaqaviy bo'lishi mumkin (samarkand.hh.uz) — asosiysini olamiz
        "url": f"https://hh.uz/vacancy/{v['vacancyId']}",
        "title": v.get("name", ""),
        "company": company.get("visibleName") or company.get("name", ""),
        "salary": _salary(v.get("compensation") or {}),
        "experience": EXPERIENCE_UZ.get(v.get("workExperience", ""), ""),
        "text": "",  # keyinroq to'ldiriladi, _fill_descriptions
        "published_at": (v.get("publicationTime") or {}).get("$", ""),
    }


def fetch(query: str) -> list[dict]:
    """Bitta so'rov bo'yicha barcha sahifalarni yig'adi."""
    results, page = [], 0
    while True:
        try:
            resp = _get(
                SEARCH_URL,
                params={
                    "text": query,
                    "area": config.HH_AREA_ID,
                    "search_period": 2,  # oxirgi 2 kun
                    "page": page,
                },
            )
            search = _state(resp.text)["vacancySearchResult"]
        except Exception as e:
            log.error("hh so'rovida xato (%s, page %s): %s", query, page, e)
            health.error(SOURCE, f"qidiruv '{query}' (page {page}): {e}")
            break

        results.extend(_clean(v) for v in search.get("vacancies", []))
        # paging bitta sahifalik natijada null bo'ladi
        pages = len((search.get("paging") or {}).get("pages", []))
        page += 1
        if page >= pages:
            break
    return results


def _description(url: str) -> str | None:
    """Vakansiya tavsifi; so'rov muvaffaqiyatsiz bo'lsa None.

    Mobil host orqali — desktop hh.uz/vacancy/<id> GitHub Actions IP'sidan
    403 qaytaradi, qidiruv sahifasi esa ishlayveradi.
    """
    try:
        resp = _get(url.replace("https://hh.uz/", "https://m.hh.uz/"),
                    headers={"Referer": SEARCH_URL})
    except Exception as e:
        log.warning("Tavsif yuklanmadi (%s): %s", url, e)
        return None
    block = BeautifulSoup(resp.text, "html.parser").select_one(
        "[data-qa=vacancy-description]"
    )
    return block.get_text(" ", strip=True)[:3000] if block else ""


def _fill_descriptions(vacancies: list[dict]) -> None:
    """Tavsiflarni yuklaydi — har biri alohida so'rov, shuning uchun limit bor."""
    capped = vacancies[: config.HH_DESC_LIMIT]
    if len(vacancies) > len(capped):
        log.info(
            "Tavsif limiti: %d ta vakansiyadan %d tasi to'liq yuklanadi",
            len(vacancies), len(capped),
        )
    failures, loaded, aborted = 0, 0, False
    for v in capped:
        text = _description(v["url"])
        if text is None:
            # Ketma-ket xatolar — bizni bloklashgan, davom etish behuda
            failures += 1
            if failures >= 3:
                log.warning("Tavsif yuklash to'xtatildi (%d marta xato)", failures)
                aborted = True
                break
            continue
        failures = 0
        v["text"] = text
        # Bo'sh matn = so'rov o'tdi, lekin selector hech nima topmadi.
        # Bu ham yuklanmagan hisoblanadi — pastdagi nisbat uni ushlaydi.
        if text:
            loaded += 1

    _report_description_health(len(capped), loaded, aborted)


def _report_description_health(planned: int, loaded: int, aborted: bool) -> None:
    """Tavsif yuklash sifatini `health` ga qayd etadi.

    Ketma-ket 3 ta xato (`aborted`) darrov ko'zga tashlanadi. Sekin
    degradatsiya esa — 25 tadan 12 tasi tarqoq yiqilishi, yoki
    `[data-qa=vacancy-description]` selektori o'zgarib hammasi bo'sh
    qaytishi — ilgari umuman sezilmasdi: manba baribir `ok ✅` bo'lib
    turardi, hisobot esa deyarli ballanmagan vakansiyalar bilan kelardi.
    """
    if not planned:
        return
    ratio = loaded / planned
    log.info("hh.uz tavsiflari: %d/%d (%.0f%%)", loaded, planned, ratio * 100)
    if aborted:
        health.error(
            SOURCE,
            f"tavsif yuklash to'xtatildi: {planned} tadan {loaded} tasi yuklandi "
            f"(ketma-ket 3 marta xato — IP bloklangan bo'lishi mumkin)",
        )
    elif ratio < config.HH_DESC_MIN_RATIO:
        health.error(
            SOURCE,
            f"tavsiflarning atigi {loaded}/{planned} tasi yuklandi ({ratio:.0%}) — "
            f"tavsifsiz vakansiya to'g'ri ballanmaydi",
        )


def collect() -> list[dict]:
    health.expect(SOURCE)
    by_url = {}
    for q in config.SEARCH_QUERIES:
        items = fetch(q)
        log.info("hh.uz '%s': %d ta vakansiya", q, len(items))
        for v in items:
            by_url.setdefault(v["url"], v)  # so'rovlar kesishadi
    all_items = list(by_url.values())
    # hh.uz qidiruv natijasi allaqachon so'rovga mos — hammasi natijaga kiradi
    health.found(SOURCE, len(all_items))
    _fill_descriptions(all_items)
    return all_items
