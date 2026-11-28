OKINA = "ʻ"
TUTUQ = "ʼ"

PAD = "<pad>"
BOS = "<bos>"
EOS = "<eos>"

SPECIAL = [PAD, BOS, EOS]

LETTERS = [
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "o" + OKINA, "g" + OKINA, TUTUQ,
]

PUNCTUATION = [" ", ",", ".", "!", "?", "-", ":", ";", "…"]

SYMBOLS = SPECIAL + LETTERS + PUNCTUATION

SYMBOL_TO_ID = {s: i for i, s in enumerate(SYMBOLS)}
ID_TO_SYMBOL = {i: s for i, s in enumerate(SYMBOLS)}

PAD_ID = SYMBOL_TO_ID[PAD]
BOS_ID = SYMBOL_TO_ID[BOS]
EOS_ID = SYMBOL_TO_ID[EOS]

MULTI_CHAR = sorted([s for s in LETTERS if len(s) > 1], key=len, reverse=True)
