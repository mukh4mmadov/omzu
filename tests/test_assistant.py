from uzllm.assistant import _extract_city, _parse_reminder, detect_lang, route
from uzllm.clean import clean_uzbek


def r(text):
    return route(clean_uzbek(text))


def test_lang():
    assert detect_lang("Toshkentda ob-havo qanday?") == "uz"
    assert detect_lang("What is the weather in London?") == "en"
    assert detect_lang("Привет") == "uz"


def test_weather_routing():
    assert r("Samarqandda ob-havo qanday?") == {"tool": "weather", "args": {"city": "Samarqand", "days": 1}}
    assert r("ertaga Buxoroda ob-havo qanday bo'ladi")["args"] == {"city": "Buxoro", "days": 2}
    assert r("What's the weather in London today?")["args"]["city"] == "London"
    assert r("ob-havo qanday?") == {"special": "weather_need_city"}
    assert _extract_city("toshkentdagi ob-havo") == "toshkent"


def test_currency_routing():
    assert r("dollar kursi qancha?") == {"tool": "currency", "args": {"code": "USD", "amount": 1.0}}
    assert r("100 dollar necha so'm?")["args"] == {"code": "USD", "amount": 100.0}
    assert r("yevro kursi")["args"]["code"] == "EUR"
    assert r("5 ming rubl qancha bo'ladi")["args"] == {"code": "RUB", "amount": 5000.0}


def test_calculator_routing():
    assert r("25*4+10")["tool"] == "calculator"
    assert r("200 ning 15 foizi qancha?")["tool"] == "calculator"
    assert r("hisobla: (12+8)/4")["tool"] == "calculator"
    assert r("Amir Temur kim?") is None


def test_reminder_and_memory_routing():
    x = r("Ertaga soat 9 da uchrashuvni eslatib qo'ying")
    assert x["tool"] == "add_reminder" and x["args"]["when"] == "ertaga 09:00"
    assert "uchrashuv" in x["args"]["text"]
    assert _parse_reminder("30 daqiqadan keyin choyni eslat")[1] == "30 daqiqa"
    assert r("eslatmalarimni ko'rsat")["tool"] == "list_reminders"
    assert r("eslat") == {"special": "reminder_need_time"}
    m = r("Eslab qol: mening tug'ilgan kunim 5-may")
    assert m["tool"] == "remember" and "5-may" in m["args"]["fact"]
    assert r("men haqimda nima bilasan?")["tool"] == "list_memories"


def test_identity_and_greeting():
    assert r("Salom") == {"special": "greeting"}
    assert r("Seni kim yaratgan?") == {"special": "identity"}
    assert r("soat necha bo'ldi?")["tool"] == "now"


def test_smalltalk_not_wikipedia():
    assert r("nima gap") == {"special": "smalltalk"}
    assert r("Qalaysiz?") == {"special": "smalltalk"}
    assert r("rahmat") == {"special": "thanks"}
    assert r("xayr") == {"special": "bye"}


def test_irrelevant_wiki_hits_are_dropped():
    from uzllm.assistant import respond
    evs = list(respond([{"role": "user", "content": "qalesan gaplar zo'rmi"}]))
    text = "".join(e["text"] for e in evs if e["type"] == "token")
    assert "Manba" not in text


def test_task_routing():
    x = r("Vazifa qo'sh: ertaga bozorga borish")
    assert x == {"tool": "add_task", "args": {"text": "bozorga borish", "due": "ertaga"}}
    assert r("vazifalarga qo'sh: kitob o'qish")["args"]["text"] == "kitob oʻqish"
    assert r("vazifalarimni ko'rsat")["tool"] == "list_tasks"
    assert r("2-vazifa bajarildi") == {"tool": "complete_task", "args": {"id": 2}}
    assert r("bozorga borishni bajardim")["args"]["text"].startswith("bozorga")
    assert r("vazifa qo'sh") == {"special": "task_need_text"}


def test_news_and_web_routing():
    assert r("so'nggi yangiliklar")["tool"] == "news"
    assert r("Kun.uz yangiliklari")["args"]["source"] == "Kun.uz"
    x = r("internetdan qidir: Elon Musk")
    assert x["tool"] == "wiki_lookup" and x["args"]["query"] == "elon musk"
    from uzllm.assistant import is_russian
    assert is_russian("Что такое фотосинтез?") and not is_russian("Ўзбекистон пойтахти қаер?")
