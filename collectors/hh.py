"""hh.uz dan vakansiyalarni rasmiy API orqali olish.

hh.ru 2025 yilda /vacancies qidiruvini avtorizatsiyasiz yopdi — tokensiz
403 forbidden qaytadi. Ilova tokenini olish uchun: python get_hh_token.py
"""
import logging
import requests

import config

log = logging.getLogger("hh")
API_URL = "https://api.hh.ru/vacancies"


def _headers() -> dict:
    h = {"User-Agent": "job-agent/1.0 (job search assistant)"}
    if config.HH_TOKEN:
        h["Authorization"] = f"Bearer {config.HH_TOKEN}"
    return h


def _clean(item: dict) -> dict:
    snippet = item.get("snippet") or {}
    salary = item.get("salary") or {}
    salary_text = ""
    if salary:
        frm, to = salary.get("from"), salary.get("to")
        cur = salary.get("currency", "")
        salary_text = f"{frm or ''}–{to or ''} {cur}".strip("– ")
    return {
        "source": "hh.uz",
        "url": item.get("alternate_url", ""),
        "title": item.get("name", ""),
        "company": (item.get("employer") or {}).get("name", ""),
        "salary": salary_text,
        "experience": (item.get("experience") or {}).get("name", ""),
        "text": " ".join(
            filter(None, [snippet.get("requirement"), snippet.get("responsibility")])
        ),
        "published_at": item.get("published_at", ""),
    }


def fetch(query: str) -> list[dict]:
    """Bitta so'rov bo'yicha barcha sahifalarni yig'adi."""
    results, page, pages = [], 0, 1
    while page < pages:
        try:
            resp = requests.get(
                API_URL,
                params={
                    "text": query,
                    "area": config.HH_AREA_ID,
                    "host": config.HH_HOST,
                    "per_page": 50,
                    "page": page,
                    "period": 2,  # oxirgi 2 kun
                },
                headers=_headers(),
                timeout=15,
            )
            if resp.status_code == 403:
                log.error(
                    "hh 403: %s. Ilova tokeni kerak — 'python get_hh_token.py'",
                    "HH_TOKEN o'rnatilmagan" if not config.HH_TOKEN
                    else "HH_TOKEN yaroqsiz yoki bekor qilingan",
                )
                break
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error("hh so'rovida xato (%s, page %s): %s", query, page, e)
            break
        pages = data.get("pages", 1)
        results.extend(_clean(i) for i in data.get("items", []))
        page += 1
    return results


def collect() -> list[dict]:
    if not config.HH_TOKEN:
        log.warning(
            "HH_TOKEN yo'q — hh.uz o'tkazib yuborildi. "
            "Token olish: python get_hh_token.py"
        )
        return []
    all_items = []
    for q in config.SEARCH_QUERIES:
        items = fetch(q)
        log.info("hh.uz '%s': %d ta vakansiya", q, len(items))
        all_items.extend(items)
    return all_items
