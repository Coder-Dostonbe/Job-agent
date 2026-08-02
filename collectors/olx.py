"""OLX.uz dan e'lonlarni scraping qilish.

Ogohlantirish: OLX'da rasmiy API yo'q, sayt tuzilishi o'zgarsa selectorlar
sinishi mumkin. Xato bo'lsa agent yiqilmaydi — shunchaki bu manba bo'sh qaytadi.
"""
import logging
import requests
from bs4 import BeautifulSoup

import config
import health

log = logging.getLogger("olx")
SOURCE = "olx.uz"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}


def _parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # OLX kartochkalari odatda data-cy="l-card" atributi bilan keladi
    for card in soup.select('[data-cy="l-card"]'):
        link = card.select_one("a[href]")
        title = card.select_one("h4, h6")
        if not (link and title):
            continue
        href = link["href"]
        if href.startswith("/"):
            href = "https://www.olx.uz" + href
        items.append({
            "source": "olx.uz",
            "url": href.split("#")[0],
            "title": title.get_text(strip=True),
            "company": "",
            "salary": "",
            "experience": "",
            "text": card.get_text(" ", strip=True)[:800],
            "published_at": "",
        })
    return items


def collect() -> list[dict]:
    health.expect(SOURCE)
    results = []
    for url in config.OLX_URLS:
        query = url.split("?q=")[-1]
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            items = _parse_page(resp.text)
            log.info("OLX %s: %d ta e'lon", query, len(items))
            if not items:
                # Sahifa keldi, lekin bironta kartochka topilmadi — deyarli
                # har doim `data-cy="l-card"` selektori eskirgani bildiradi.
                health.error(SOURCE, f"'{query}': sahifa ochildi, lekin 0 ta "
                                     f"kartochka topildi (selector eskirganmi?)")
            health.found(SOURCE, len(items))
            results.extend(items)
        except Exception as e:
            log.error("OLX xato (%s): %s", url, e)
            health.error(SOURCE, f"'{query}': {e}")
    return results
