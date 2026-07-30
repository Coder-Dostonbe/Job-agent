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

import requests
from bs4 import BeautifulSoup

import config

log = logging.getLogger("hh")

SEARCH_URL = "https://hh.uz/search/vacancy"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.9",
}
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
            resp = requests.get(
                SEARCH_URL,
                params={
                    "text": query,
                    "area": config.HH_AREA_ID,
                    "search_period": 2,  # oxirgi 2 kun
                    "page": page,
                },
                headers=HEADERS,
                timeout=20,
            )
            resp.raise_for_status()
            search = _state(resp.text)["vacancySearchResult"]
        except Exception as e:
            log.error("hh so'rovida xato (%s, page %s): %s", query, page, e)
            break

        results.extend(_clean(v) for v in search.get("vacancies", []))
        # paging bitta sahifalik natijada null bo'ladi
        pages = len((search.get("paging") or {}).get("pages", []))
        page += 1
        if page >= pages:
            break
    return results


def _description(url: str) -> str:
    """Vakansiya sahifasidan to'liq tavsifni oladi."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        block = BeautifulSoup(resp.text, "html.parser").select_one(
            "[data-qa=vacancy-description]"
        )
        return block.get_text(" ", strip=True)[:3000] if block else ""
    except Exception as e:
        log.warning("Tavsif yuklanmadi (%s): %s", url, e)
        return ""


def _fill_descriptions(vacancies: list[dict]) -> None:
    """Tavsiflarni yuklaydi — har biri alohida so'rov, shuning uchun limit bor."""
    capped = vacancies[: config.HH_DESC_LIMIT]
    if len(vacancies) > len(capped):
        log.info(
            "Tavsif limiti: %d ta vakansiyadan %d tasi to'liq yuklanadi",
            len(vacancies), len(capped),
        )
    for v in capped:
        v["text"] = _description(v["url"])


def collect() -> list[dict]:
    by_url = {}
    for q in config.SEARCH_QUERIES:
        items = fetch(q)
        log.info("hh.uz '%s': %d ta vakansiya", q, len(items))
        for v in items:
            by_url.setdefault(v["url"], v)  # so'rovlar kesishadi
    all_items = list(by_url.values())
    _fill_descriptions(all_items)
    return all_items
