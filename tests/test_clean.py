from uzllm.clean import clean_uzbek

O = "ʻ"
T = "ʼ"


def test_keeps_case_and_digits():
    assert clean_uzbek("O'zbekiston 1991-yil") == f"O{O}zbekiston 1991-yil"


def test_cyrillic_doc_converted():
    assert clean_uzbek("Тошкент — Ўзбекистон пойтахти.") == f"Toshkent — O{O}zbekiston poytaxti."


def test_tutuq_and_quotes():
    assert clean_uzbek("ma'no 'salom'") == f"ma{T}no 'salom'"
