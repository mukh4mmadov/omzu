import re
import unicodedata

from .cyrillic import cyrillic_to_latin, has_cyrillic
from .numbers import expand_numbers
from .symbols import (
    BOS_ID, EOS_ID, ID_TO_SYMBOL, MULTI_CHAR, OKINA, SYMBOL_TO_ID, TUTUQ,
)

_APOSTROPHES = "'`‘’ʻʼ´ʹ"

_SYMBOL_WORDS = {
    "&": " va ",
    "+": " plyus ",
    "=": " teng ",
    "$": " dollar ",
    "€": " yevro ",
    "№": " raqam ",
}


def _fix_apostrophes(text: str) -> str:
    out = []
    for i, ch in enumerate(text):
        if ch not in _APOSTROPHES:
            out.append(ch)
            continue
        prev = text[i - 1] if i > 0 else ""
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if prev in ("o", "g"):
            out.append(OKINA)
        elif prev.isalpha() and nxt.isalpha():
            out.append(TUTUQ)
    return "".join(out)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    if has_cyrillic(text):
        text = cyrillic_to_latin(text)
    text = text.lower()
    text = _fix_apostrophes(text)

    for sym, word in _SYMBOL_WORDS.items():
        text = text.replace(sym, word)
    text = expand_numbers(text)

    text = re.sub(r"\s+[-–—]+\s+|[–—]", ", ", text)
    text = text.replace("...", "…")
    text = re.sub(r"[()\[\]{}]", ",", text)

    allowed = set("".join(SYMBOL_TO_ID.keys()))
    text = "".join(ch if ch in allowed else " " for ch in text)

    text = re.sub(r"\s+([,.!?:;…])", r"\1", text)
    text = re.sub(r"([,.!?:;…])(?=[^\s,.!?:;…])", r"\1 ", text)
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    return text


def tokenize(text: str) -> list[str]:
    tokens, i = [], 0
    while i < len(text):
        for mc in MULTI_CHAR:
            if text.startswith(mc, i):
                tokens.append(mc)
                i += len(mc)
                break
        else:
            if text[i] in SYMBOL_TO_ID:
                tokens.append(text[i])
            i += 1
    return tokens


def text_to_ids(text: str, add_bos_eos: bool = True) -> list[int]:
    ids = [SYMBOL_TO_ID[t] for t in tokenize(normalize(text))]
    if add_bos_eos:
        ids = [BOS_ID] + ids + [EOS_ID]
    return ids


def ids_to_text(ids: list[int]) -> str:
    return "".join(ID_TO_SYMBOL[i] for i in ids if i not in (BOS_ID, EOS_ID) and i in ID_TO_SYMBOL)
