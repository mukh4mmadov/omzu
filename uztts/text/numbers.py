import re

from .symbols import OKINA

_o = "o" + OKINA

ONES = ["nol", "bir", "ikki", "uch", f"t{_o}rt", "besh", "olti", "yetti", "sakkiz", f"t{_o}qqiz"]
TENS = ["", f"{_o}n", "yigirma", f"{_o}ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", f"t{_o}qson"]
SCALES = [(10**12, "trillion"), (10**9, "milliard"), (10**6, "million"), (1000, "ming")]


def _below_thousand(n: int) -> list[str]:
    words = []
    h, r = divmod(n, 100)
    if h:
        words += [ONES[h], "yuz"]
    t, o = divmod(r, 10)
    if t:
        words.append(TENS[t])
    if o:
        words.append(ONES[o])
    return words


def number_to_words(n: int) -> str:
    if n == 0:
        return "nol"
    if n < 0:
        return "minus " + number_to_words(-n)
    words = []
    for value, name in SCALES:
        if n >= value:
            count, n = divmod(n, value)
            words += _below_thousand(count) + [name]
    words += _below_thousand(n)
    return " ".join(words)


def ordinal_to_words(n: int) -> str:
    w = number_to_words(n)
    return w + ("nchi" if w[-1] in "aeiou" else "inchi")


def _digits_to_words(digits: str) -> str:
    zeros = len(digits) - len(digits.lstrip("0"))
    rest = digits.lstrip("0")
    parts = ["nol"] * zeros
    if rest:
        parts.append(number_to_words(int(rest)))
    return " ".join(parts)


def expand_numbers(text: str) -> str:
    text = re.sub(r"(?<=\d)[  ](?=\d{3}\b)", "", text)
    text = re.sub(r"(\d)\s*%", r"\1 foiz", text)
    text = re.sub(
        r"\b(\d{1,2}):(\d{2})\b",
        lambda m: f"{number_to_words(int(m.group(1)))} {_digits_to_words(m.group(2))}",
        text,
    )
    text = re.sub(
        r"\b(\d+)\s*[-–]\s*(\d+)\b",
        lambda m: f"{number_to_words(int(m.group(1)))} {number_to_words(int(m.group(2)))}",
        text,
    )
    text = re.sub(r"\b(\d+)-(?=\s|[^\W\d_]|$)", lambda m: ordinal_to_words(int(m.group(1))) + " ", text)
    text = re.sub(
        r"\b(\d+)[.,](\d+)\b",
        lambda m: f"{number_to_words(int(m.group(1)))} butun {_digits_to_words(m.group(2))}",
        text,
    )
    text = re.sub(r"\d+", lambda m: number_to_words(int(m.group(0))), text)
    return text
