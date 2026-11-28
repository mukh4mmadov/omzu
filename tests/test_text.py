from uztts.text import ids_to_text, normalize, number_to_words, ordinal_to_words, text_to_ids, tokenize

O = "oʻ"
G = "gʻ"
T = "ʼ"


def test_numbers():
    assert number_to_words(0) == "nol"
    assert number_to_words(7) == "yetti"
    assert number_to_words(125) == "bir yuz yigirma besh"
    assert number_to_words(2024) == "ikki ming yigirma t" + O + "rt"
    assert number_to_words(1_500_000) == "bir million besh yuz ming"


def test_ordinals():
    assert ordinal_to_words(1) == "birinchi"
    assert ordinal_to_words(2) == "ikkinchi"
    assert ordinal_to_words(20) == "yigirmanchi"
    assert ordinal_to_words(3) == "uchinchi"


def test_apostrophes():
    for ap in ["'", "`", "‘", "’", "ʻ"]:
        assert normalize(f"o{ap}zbek tog{ap}") == f"{O}zbek to{G}"
    assert normalize("ma'no san'at") == f"ma{T}no san{T}at"


def test_cyrillic():
    assert normalize("Ўзбекистон") == f"{O}zbekiston"
    assert normalize("Ер юзи") == "yer yuzi"
    assert normalize("тоғ ва қишлоқ") == f"to{G} va qishloq"


def test_full_sentence():
    s = normalize("Bugun 15% chegirma! Soat 14:30 da 2-qavatga keling.")
    assert s == f"bugun {O}n besh foiz chegirma! soat {O}n t{O}rt {O}ttiz da ikkinchi qavatga keling."


def test_tokenize_and_roundtrip():
    toks = tokenize(f"{O}zbek")
    assert toks == [O, "z", "b", "e", "k"]
    ids = text_to_ids("O'zbekiston")
    assert ids_to_text(ids) == f"{O}zbekiston"
