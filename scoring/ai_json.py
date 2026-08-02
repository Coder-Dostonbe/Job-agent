"""Model javobidan JSON'ni xavfsiz ajratib olish.

Ikkala AI moduli ham (`ai_filter`, `ai_scorer`) modeldan JSON so'raydi va
ilgari javobni to'g'ridan-to'g'ri `json.loads()` ga berardi. Bu ikki joyda
sinadi:

1. **Atrofidagi matn.** Model ba'zan "Mana javob:" deb boshlaydi yoki ```json
   bloki ichiga o'raydi. Javobning o'zi butun, lekin `json.loads()` yiqiladi
   va butun tahlil (puli to'langan) bekorga ketadi.
2. **API xato javobi.** `resp.json()["content"][0]["text"]` xato javobda
   `KeyError`/`IndexError` beradi — sababi esa aynan `error.message` ichida
   yotadi va logga chiqmaydi.

Shuning uchun ajratish alohida modulga chiqarildi: bir joyda tuzatilsa,
ikkala chaqiruvchi ham foyda ko'radi.
"""
import json
import re

# ```json ... ``` o'ramini olib tashlash
_FENCE = re.compile(r"```(?:json)?", re.IGNORECASE)


def content_text(payload: dict) -> str:
    """Anthropic Messages API javobidan matnni oladi.

    Xato javobini alohida ushlaydi — aks holda uning sababi `KeyError:
    'content'` ortida yo'qoladi. Javob `max_tokens` ga yetib kesilgan bo'lsa
    ham buni aytadi: kesilgan JSON'ni tiklab bo'lmaydi, sababi bilinsin.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"kutilmagan javob turi: {type(payload).__name__}")
    if payload.get("type") == "error":
        message = (payload.get("error") or {}).get("message", "noma'lum xato")
        raise ValueError(f"API xatosi: {message}")
    blocks = payload.get("content")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("javobda 'content' bo'sh")
    text = "".join(
        b.get("text", "") for b in blocks if isinstance(b, dict)
    ).strip()
    if not text:
        raise ValueError("javob matni bo'sh")
    if payload.get("stop_reason") == "max_tokens":
        raise ValueError("javob max_tokens chegarasida kesildi — JSON to'liq emas")
    return text


def parse(raw: str):
    """Matndan JSON obyekt/massivni ajratib qaytaradi.

    Muvaffaqiyatsiz bo'lsa `ValueError` ko'taradi — chaqiruvchi uni ushlab
    o'z xatti-harakatini tanlaydi (odatda: shu bitta natijadan voz kechish,
    butun run'dan emas).
    """
    text = _FENCE.sub("", raw or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    snippet = _first_json(text)
    if snippet is None:
        raise ValueError(f"javobda to'liq JSON topilmadi: {text[:120]!r}")
    return json.loads(snippet)


def _first_json(text: str) -> str | None:
    """Birinchi `{`/`[` dan unga mos yopiluvchi qavsgacha bo'lgan bo'lak.

    Qavslar sanoqda; qo'shtirnoq ichidagi qavslar hisobga olinmaydi
    (`{"reason": "narx {noma'lum}"}` singari holatlar uchun).
    """
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None  # ochildi-yu yopilmadi — javob kesilgan
