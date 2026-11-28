import re
import unicodedata

from uztts.text.cyrillic import cyrillic_to_latin

OKINA = "ʻ"
TUTUQ = "ʼ"
_APOS = "'`‘’ʻʼ´ʹ"
_APOS_RE = re.compile(f"[{re.escape(_APOS)}]")


def _fix_apostrophes(text: str) -> str:
    def repl(m: re.Match) -> str:
        i = m.start()
        prev = text[i - 1] if i > 0 else ""
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if prev in "oOgG":
            return OKINA
        if prev.isalpha() and nxt.isalpha():
            return TUTUQ
        return "'"
    return _APOS_RE.sub(repl, text)


def cyrillic_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum("Ѐ" <= c <= "ӿ" for c in letters) / len(letters)


def clean_uzbek(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    if cyrillic_ratio(text) > 0.3:
        text = cyrillic_to_latin(text)
    text = _fix_apostrophes(text)
    return _tidy(text)


def clean_english(text: str) -> str:
    return _tidy(unicodedata.normalize("NFC", text))


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
