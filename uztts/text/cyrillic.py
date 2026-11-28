from .symbols import OKINA, TUTUQ

_VOWELS_CYR = set("аеёиоуэюяўАЕЁИОУЭЮЯЎ")

_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l",
    "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "s", "ч": "ch",
    "ш": "sh", "щ": "sh", "ъ": TUTUQ, "ы": "i", "ь": "", "э": "e",
    "ю": "yu", "я": "ya", "ў": "o" + OKINA, "қ": "q", "ғ": "g" + OKINA,
    "ҳ": "h",
}


def has_cyrillic(text: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in text)


def cyrillic_to_latin(text: str) -> str:
    out = []
    for i, ch in enumerate(text):
        low = ch.lower()
        if low == "е":
            prev = text[i - 1] if i > 0 else " "
            lat = "ye" if (not prev.isalpha() or prev in _VOWELS_CYR or prev in "ъЪ") else "e"
        elif low == "ц":
            prev = text[i - 1] if i > 0 else " "
            lat = "ts" if (prev.isalpha() and prev not in _VOWELS_CYR) else "s"
        elif low in _MAP:
            lat = _MAP[low]
        else:
            out.append(ch)
            continue
        if ch != low and lat:
            lat = lat[0].upper() + lat[1:]
        out.append(lat)
    return "".join(out)
