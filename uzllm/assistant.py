import re
import time
from collections.abc import Iterator
from pathlib import Path

from uzllm import knowledge, tools
from uzllm.clean import clean_uzbek

NAME = "OMZU"
CREATOR = "Ozodbek Muhammadov"
ROOT = Path(__file__).resolve().parent.parent
CHAT_MODEL = ROOT / "checkpoints" / "chat" / "best.pt"
TOKENIZER = ROOT / "data" / "tokenizer.json"

SYSTEM_PROMPT = (
    f"Siz {NAME} — {CREATOR} tomonidan noldan yaratilgan sun'iy intellekt yordamchisisiz. "
    "Foydalanuvchiga \"siz\" deb murojaat qilasiz. Javoblaringiz jiddiy, aniq va qisqa. "
    "Savol qaysi tilda bo'lsa, o'sha tilda javob berasiz. Bilmagan narsangizni to'qimaysiz — "
    "\"aniq ma'lumotim yo'q\" deysiz. Berilgan kontekst bo'lsa, faqat unga tayanib javob berasiz."
)

_EN_WORDS = {"the", "is", "are", "what", "who", "how", "when", "where", "why", "you", "your", "my",
             "please", "can", "do", "does", "a", "an", "of", "in", "to", "and", "weather", "time", "hello", "hi"}
_UZ_HINTS = re.compile(r"[ʻʼ]|\b(va|bu|nima|qanday|qancha|necha|menga|siz|sen|uchun|bilan|qayerda|kim|salom|bormi|kerak)\b|(ning|lar|dagi|ga|da|ni)\b")


_RU_WORDS = re.compile(r"\b(что|кто|как|где|когда|почему|это|такое|расскажи|мне|про|о|в|на|и|или|сколько|какой|какая)\b")


def is_russian(raw: str) -> bool:
    low = raw.lower()
    if not re.search(r"[Ѐ-ӿ]", low) or re.search(r"[ўқғҳ]", low):
        return False
    return bool(re.search(r"[ыэщь]", low) or _RU_WORDS.search(low))


def detect_lang(text: str) -> str:
    low = text.lower()
    if re.search(r"[Ѐ-ӿ]", low):
        return "uz"
    words = re.findall(r"[a-zʻʼ']+", low)
    en = sum(w in _EN_WORDS for w in words)
    uz = len(_UZ_HINTS.findall(low))
    return "en" if en > uz else "uz"


_CURRENCIES = {
    "USD": ["dollar", "usd", "$"], "EUR": ["yevro", "evro", "euro", "eur", "€"],
    "RUB": ["rubl", "rub", "₽"], "GBP": ["funt", "gbp", "£"], "CNY": ["yuan", "cny"],
    "KZT": ["tenge", "kzt"], "TRY": ["lira", "try"], "JPY": ["iyena", "yen", "jpy"],
    "KRW": ["von", "won", "krw"], "AED": ["dirham", "aed"],
}
_WEATHER_WORDS = ("ob-havo", "obhavo", "ob havo", "havo qanday", "harorat", "weather", "temperature",
                  "yomg'ir", "yomgʻir", "qor yog")
_CITY_SUFFIXES = ("dagi", "ning", "da", "ga", "ni", "dan")


def _amount_before(text: str, word: str) -> float:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ming\s*)?" + re.escape(word), text)
    if not m:
        return 1.0
    val = float(m.group(1).replace(",", "."))
    if re.search(r"\d\s*ming\s*" + re.escape(word), text):
        val *= 1000
    return val


def _extract_city(text: str) -> str | None:
    m = re.search(r"\b(?:in|for|at)\s+([A-Z][\w\-ʻʼ]+(?:\s+[A-Z][\w\-ʻʼ]+)?)", text)
    if m:
        return m.group(1)
    t = re.sub(r"[?.!,:]", " ", text)
    t = re.sub(r"\b\w+[ʼ']s\b", " ", t)
    stop = {"ob-havo", "obhavo", "ob", "havo", "qanday", "bugun", "ertaga", "hozir", "harorat", "necha",
            "daraja", "weather", "in", "the", "what", "is", "today", "tomorrow", "like", "how", "s",
            "haftalik", "hafta", "kunlik", "prognoz", "menga", "ayting", "ayt", "qancha", "bo'ladi",
            "boʻladi", "yomg'ir", "yomgʻir", "yog'adimi", "yogʻadimi", "qor", "bormi", "for"}
    cands = []
    for w in t.split():
        lw = w.lower()
        if lw in stop or len(lw) < 3 or lw.isdigit():
            continue
        base = w
        for suf in _CITY_SUFFIXES:
            if lw.endswith(suf) and len(lw) - len(suf) >= 3:
                base = w[: -len(suf)]
                break
        cands.append((w[0].isupper(), base))
    if not cands:
        return None
    caps = [c for up, c in cands if up]
    return (caps or [cands[-1][1]])[0]


_TIME_RE = re.compile(
    r"(ertaga|indinga)?\s*(?:soat\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:da|ga)\b"
    r"|(\d+)\s*(daqiqa|minut|soat)(?:dan)?\s*(?:keyin|so'ng|soʻng)?", re.I)


def _parse_reminder(text: str) -> tuple[str, str] | None:
    low = text.lower()
    m = re.search(r"(\d+)\s*(daqiqa|minut|soat)\w*\s*(?:dan\s*)?(keyin|so['ʻ]ng)", low)
    when = None
    span = None
    if m:
        when, span = f"{m.group(1)} {m.group(2)}", m.span()
    else:
        m = re.search(r"(ertaga|indinga)?\s*(?:soat\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:da|ga)\b", low)
        if m:
            hh, mm = int(m.group(2)), int(m.group(3) or 0)
            when = f"{(m.group(1) + ' ') if m.group(1) else ''}{hh:02d}:{mm:02d}"
            span = m.span()
    if not when:
        return None
    rest = (low[: span[0]] + " " + low[span[1]:])
    rest = re.sub(r"\b(eslatib\s+qo['ʻ]y\w*|eslat\w*|iltimos|menga|ni\s+eslat\w*)\b", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" ,.!?")
    rest = re.sub(r"(\w{3,})ni$", r"\1", rest)
    return (rest or "eslatma"), when


def route(text: str) -> dict | None:
    low = text.lower().strip()

    if re.fullmatch(r"(assalomu? ?alaykum|salom|hello|hi|hey|salom alaykum)[!. ]*", low):
        return {"special": "greeting"}
    if re.search(r"^(katta )?(rahmat|tashakkur|thanks?|thank you)\b", low):
        return {"special": "thanks"}
    if re.search(r"^(xayr|ko['ʻ]rishguncha|bye|goodbye)\b", low):
        return {"special": "bye"}
    if re.search(r"^(nima gap\w*|qalaysi?z?|qalaysan|qalesa?n|yaxshimisi?z|yaxshimisan|ishlar qalay|nima yangilik\w*|"
                 r"how are you|what[ʼ']?s up)\b", low):
        return {"special": "smalltalk"}
    if re.fullmatch(r"(sen |siz |endi |hozir )?(n[ie]?ma\w*|nm\w+)\s+q(i)?l\w*\s*(ola\w*|a?san|a?siz)?[?!. ]*", low) or re.search(
            r"^(qanday yordam\w*|imkoniyat\w*|what can you do|how can you help|help|yordam)\b", low):
        return {"special": "help"}
    if re.search(r"(isming|sen kimsan|siz kimsiz|kim yaratgan|seni kim|sizni kim|who are you|your name|who (made|created|built) you)", low):
        return {"special": "identity"}
    if re.search(r"(yoshing|yoshingiz|necha yoshdasan|necha yoshdasiz|nechchi yoshdasan|nechchi yoshdasiz|sen qachon (yaratil|tug)|siz qachon (yaratil|tug)|how old are you|your age|when were you (made|born|created))", low):
        return {"special": "age"}
    if re.search(r"(qayerda(n)?san|qayerlik|qayerdansiz|jinsing|erkakmisan|ayolmisan|oilang|do['ʻ]sting|are you (a )?(man|woman|human|real)|where are you from)", low):
        return {"special": "about"}
    if re.search(r"\b(lox\w*|ahmoq\w*|tentak\w*|jinni\w*|dalbayob\w*|gandon\w*|yaramas\w*|aqlsiz\w*|stupid|idiot|dumb)\b", low) and len(low.split()) <= 4:
        return {"special": "rude"}

    if re.fullmatch(r"(nega|nimaga|nima uchun|qanday|nima|kim|qachon|qayerda|why|how|what|who|when|where)\s*[?!. ]*", low):
        return {"special": "unclear"}
    if re.fullmatch(r"(can|could|do|will) (you|u|ya)[\w\s]{0,25}[?!. ]*", low) and not re.search(r"\d", low):
        return {"special": "help"}
    if re.search(r"(yordam bera olasan\w*|yordam berasan\w*|yordam bera olasiz\w*|can you help|could you help)", low) and len(low.split()) <= 7:
        return {"special": "help"}
    if re.search(r"(men haqimda nima|nimalarni eslab qolding|what do you (know|remember) about me)", low):
        return {"tool": "list_memories", "args": {}}
    m = re.search(r"(?:buni\s+)?eslab\s+qol\w*[:,]?\s*(.*)|remember (?:that )?(.*)", text, re.I)
    if m:
        fact = (m.group(1) or m.group(2) or "").strip(" .:")
        fact = re.sub(r"\s*(ni|buni)?\s*eslab\s+qol\w*", "", fact, flags=re.I).strip(" .:")
        if not fact:
            fact = re.sub(r"\s*(buni\s+)?eslab\s+qol\w*.*$", "", text, flags=re.I).strip(" .:")
        if fact:
            return {"tool": "remember", "args": {"fact": fact}}

    if re.search(r"\b(yangilik\w*|news|xabarlar\w*|nima gaplar dunyoda)\b", low) and not re.search(r"\bqo['ʻ]sh", low):
        src = next((s for s in tools.NEWS_FEEDS if s.split(".")[0].lower() in low), None)
        return {"tool": "news", "args": {"limit": 8, "source": src}}
    m = re.search(r"^(?:internetdan|vikipediya\w*|wikipedia\w*|search)\s*(?:dan)?\s*(?:qidir\w*|top\w*|for)?\s*:?\s*(.+)$", low)
    if m and len(m.group(1).strip()) > 1:
        q = m.group(1).strip(" ?.!")
        wl = "ru" if re.search(r"[Ѐ-ӿ]", q) and not re.search(r"[ўқғҳ]", q) else ("en" if detect_lang(q) == "en" else "uz")
        return {"tool": "wiki_lookup", "args": {"query": q, "lang": wl}}

    task_add = re.search(r"(vazifa\w*|ro['ʻ]yxat\w*|to-?do\w*)\s*(?:ga|lar\w*)?\s*qo['ʻ]sh\w*|^vazifa\s*:", low)
    if task_add or re.search(r"\bqo['ʻ]sh\w*\b.*\b(vazifa\w*|to-?do)\b", low):
        t = re.sub(r"(?i)\b(vazifa\w*|ro['ʻ]yxat\w*|to-?do\w*)\b|\bqo['ʻ]sh\w*\b|\biltimos\b|\bmenga\b|:", " ", text)
        due = None
        m = re.search(r"\b(bugun|ertaga|indinga|\d{1,2}\.\d{1,2}(?:\.\d{4})?)\b", t.lower())
        if m:
            due = m.group(1)
            t = t[: m.start()] + t[m.end():]
        t = re.sub(r"\s+", " ", t).strip(" ,.-")
        t = re.sub(r"(\w{3,})ni$", r"\1", t)
        return {"tool": "add_task", "args": {"text": t, "due": due}} if t else {"special": "task_need_text"}
    m = re.search(r"(\d+)\s*-?\s*(?:raqamli\s*)?vazifa\w*\s*(?:ni\s*)?(bajarildi|bajardim|tugadi|tugatdim)", low) or \
        re.search(r"(bajarildi|bajardim|tugatdim)\s*:?\s*(\d+)\b", low)
    if m:
        num = m.group(1) if m.group(1).isdigit() else m.group(2)
        return {"tool": "complete_task", "args": {"id": int(num)}}
    m = re.search(r"^(.{3,}?)\s*(?:ni\s+)?(bajardim|bajarildi|tugatdim)\b", low)
    if m and not re.search(r"\?|qanday|nima", low):
        return {"tool": "complete_task", "args": {"text": m.group(1)}}
    if re.search(r"(vazifalar\w*|to-?do\w*|qiladigan ishlar\w*|ishlarim\w*)", low):
        return {"tool": "list_tasks", "args": {}}

    if re.search(r"eslatmalar\w*|reminders", low) and not re.search(r"\d", low):
        return {"tool": "list_reminders", "args": {}}
    if re.search(r"eslat|remind", low):
        parsed = _parse_reminder(text)
        if parsed:
            return {"tool": "add_reminder", "args": {"text": parsed[0], "when": parsed[1]}}
        return {"special": "reminder_need_time"}

    if re.search(r"\b(kurs\w*|valyuta\w*|exchange rate)", low) or (
            re.search(r"\b(necha|qancha|how much)\b", low) and any(w in low for ws in _CURRENCIES.values() for w in ws)):
        for code, words in _CURRENCIES.items():
            for w in words:
                if re.search(r"(?<![a-z])" + re.escape(w), low):
                    return {"tool": "currency", "args": {"code": code, "amount": _amount_before(low, w)}}
        return {"tool": "currency", "args": {"code": "USD", "amount": 1}}

    if any(w in low for w in _WEATHER_WORDS) and not re.search(r"(nima uchun|nega|qanday qilib|why|how does)", low):
        days = 7 if re.search(r"hafta|week", low) else (2 if re.search(r"ertaga|tomorrow", low) else 1)
        city = _extract_city(text)
        if not city:
            return {"special": "weather_need_city"}
        return {"tool": "weather", "args": {"city": city, "days": days}}

    if re.search(r"(soat necha|vaqt necha|bugun (necha|qaysi|qanday) kun|bugungi sana|what time|today's date|what day)", low):
        return {"tool": "now", "args": {}}

    expr = re.sub(r"(what is|how much is|hisobla\w*|calculate|necha bo['ʻ]ladi|qancha bo['ʻ]ladi|nechaga teng|nechiga teng|"
                  r"nechchi|nechaga|necha|qancha|natija\w*|equals?|teng|=|\?|:)", " ", low)
    for w, o in (("times", "*"), ("multiplied by", "*"), ("plus", "+"), ("minus", "-"), ("divided by", "/"), ("koʻpaytirilsa", "*")):
        expr = expr.replace(w, f" {o} ")
    expr = re.sub(r"(\d+(?:[.,]\d+)?)\s*ning\s*(\d+)[- ]*(?:chi\s*)?darajasi", r"(\g<1>**\g<2>)", expr)
    expr = re.sub(r"(\d+(?:[.,]\d+)?)\s*ning\s*(\d+(?:[.,]\d+)?)\s*(?:foizi|%)", r"(\g<1>*\g<2>/100)", expr)
    expr = re.sub(r"(?<=\d)\s*[x×]\s*(?=\d)", "*", expr).replace("foiz", "%").strip()
    if re.fullmatch(r"[\d\s.,+\-*/^()%×÷a-z]*\d[\d\s.,+\-*/^()%×÷]*", expr) and re.search(r"\d\s*[-+*/^%×÷]|sqrt|\(", expr):
        return {"tool": "calculator", "args": {"expression": expr}}
    return None


def _fmt_num(x: float) -> str:
    s = f"{x:,.2f}".rstrip("0").rstrip(".")
    return s.replace(",", " ")


def compose_tool_answer(tool: str, args: dict, res: dict, lang: str) -> str:
    uz = lang == "uz"
    if "error" in res:
        return (f"Kechirasiz, bajarib bo'lmadi: {res['error']}." if uz else f"Sorry, that failed: {res['error']}.")
    if tool == "weather":
        n = res["now"]
        head = (f"**{res['city']}** — hozir **{n['temp_c']:+.0f}°C**, {n['sky']}. "
                f"His qilinishi {n['feels_like_c']:+.0f}°C, namlik {n['humidity']}%, shamol {n['wind_kmh']:.0f} km/soat."
                if uz else
                f"**{res['city']}** — now **{n['temp_c']:+.0f}°C**, {n['sky']}. Feels like {n['feels_like_c']:+.0f}°C, "
                f"humidity {n['humidity']}%, wind {n['wind_kmh']:.0f} km/h.")
        fc = res["forecast"]
        if len(fc) == 2:
            d = fc[1]
            head += (f"\n\nErtaga: {d['min_c']:+.0f}…{d['max_c']:+.0f}°C, {d['sky']}, yogʻingarchilik ehtimoli {d['rain_chance']}%."
                     if uz else f"\n\nTomorrow: {d['min_c']:+.0f}…{d['max_c']:+.0f}°C, {d['sky']}, rain chance {d['rain_chance']}%.")
        elif len(fc) > 2:
            lo, hi = min(d["min_c"] for d in fc), max(d["max_c"] for d in fc)
            rainy = [d for d in fc if d["rain_chance"] >= 50 or re.search(r"yomg|jala|qor|momaq", d["sky"])]
            head += (f"\n\nHafta davomida harorat {lo:+.0f}…{hi:+.0f}°C oraligʻida. "
                     + (f"Yogʻingarchilik ehtimoli yuqori kunlar: {len(rainy)} ta." if rainy else "Yogʻingarchilik kutilmayapti.")
                     if uz else f"\n\nThis week: {lo:+.0f}…{hi:+.0f}°C. " + (f"{len(rainy)} rainy day(s) likely." if rainy else "No rain expected."))
        return head
    if tool == "currency":
        if res["amount"] != 1:
            return (f"{_fmt_num(res['amount'])} {res['currency']} = **{_fmt_num(res['total_uzs'])} soʻm** "
                    f"(Markaziy bank kursi: 1 {res['currency']} = {_fmt_num(res['rate_uzs'])} soʻm, {res['date']}).")
        ch = res["change"]
        trend = (f", kechagidan {'+' if ch > 0 else ''}{_fmt_num(ch)}" if ch else "")
        return (f"1 {res['currency']} ({res['name']}) = **{_fmt_num(res['rate_uzs'])} soʻm**{trend}. "
                f"Manba: Markaziy bank, {res['date']}." if uz else
                f"1 {res['currency']} = **{_fmt_num(res['rate_uzs'])} UZS** (Central Bank of Uzbekistan, {res['date']}).")
    if tool == "calculator":
        r = res["result"]
        return f"**{_fmt_num(r) if isinstance(r, (int, float)) else r}**"
    if tool == "add_reminder":
        return (f"Eslatma qoʻyildi: **{res['text']}** — {res['due']}." if uz else
                f"Reminder set: **{res['text']}** — {res['due']}.")
    if tool == "list_reminders":
        items = res["reminders"]
        if not items:
            return "Faol eslatmalar yoʻq." if uz else "No active reminders."
        return ("Eslatmalaringiz:\n" if uz else "Your reminders:\n") + "\n".join(
            f"- {r['due']} — {r['text']}" for r in items)
    if tool == "remember":
        return f"📝 Eslab qoldim: «{res['saved']}»." if uz else f"📝 Noted: “{res['saved']}”."
    if tool == "list_memories":
        items = res["memories"]
        if not items:
            return "Hozircha siz haqingizda hech narsa saqlanmagan." if uz else "I haven't saved anything about you yet."
        return ("Siz haqingizda bilganlarim:\n" if uz else "What I know about you:\n") + "\n".join(
            f"- {m['fact']}" for m in items)
    if tool == "news":
        return (f"Soʻnggi yangiliklar ({len(res['items'])} ta). Batafsil oʻqish uchun sarlavhani bosing."
                if uz else f"Latest news ({len(res['items'])}). Click a headline to read more.")
    if tool == "wiki_lookup":
        body = _first_sentences(res["text"], n=3, max_chars=600) if res.get("text") else ""
        return f"{body}\n\n*Manba: [{res['title']} — Vikipediya ({res['lang']})]({res['url']})*" if uz else \
            f"{body}\n\n*Source: [{res['title']} — Wikipedia ({res['lang']})]({res['url']})*"
    if tool == "add_task":
        due = f" — muddat: {res['due']}" if res.get("due") else ""
        return f"✅ Vazifa qoʻshildi: **{res['text']}**{due}." if uz else f"✅ Task added: **{res['text']}**{due}."
    if tool == "list_tasks":
        items = res["tasks"]
        if not items:
            return "Hozircha vazifalar yoʻq. Qoʻshish uchun: «vazifa qoʻsh: …»" if uz else "No tasks yet."
        return (f"Sizda **{len(items)} ta** bajarilmagan vazifa bor. Bajarilganini belgilab qoʻying."
                if uz else f"You have **{len(items)}** open task(s).")
    if tool == "complete_task":
        return f"👏 Bajarildi: ~~{res['text']}~~" if uz else f"👏 Done: ~~{res['text']}~~"
    if tool == "now":
        return (f"Bugun {res['date']}, {res['weekday']}. Soat **{res['time']}**." if uz else
                f"Today is {res['date']} ({res['weekday']}). Time: **{res['time']}**.")
    return str(res)


SPECIAL = {
    "greeting": {"uz": f"Assalomu alaykum. Men {NAME}. Sizga qanday yordam bera olaman?",
                 "en": f"Hello. I'm {NAME}. How can I help you?"},
    "identity": {"uz": f"Men **{NAME}** — sun'iy intellekt yordamchisiman. Meni **{CREATOR}** noldan yaratgan: "
                       "tokenizer, til modeli va barcha vositalar shu loyiha doirasida yozilgan.",
                 "en": f"I'm **{NAME}**, an AI assistant built from scratch by **{CREATOR}**."},
    "age": {"uz": f"Men dasturman, shuning uchun yoshim yoʻq. {NAME} yaqinda, {CREATOR} tomonidan yaratilgan va hali oʻrganish bosqichida.",
            "en": f"I'm a program, so I don't have an age. {NAME} was created recently by {CREATOR} and is still learning."},
    "about": {"uz": f"Men odam emasman, sunʼiy intellekt dasturiman. Meni {CREATOR} yaratgan, shuning uchun jinsim, oilam yoki yashash joyim yoʻq.",
              "en": f"I'm not a person, I'm an AI program built by {CREATOR}, so I have no gender, family or hometown."},
    "unclear": {"uz": "Savolingizni tushunmadim. Iltimos, aniqroq yozing, masalan: «Amir Temur kim?» yoki «nimalar qila olasan?».",
                "en": "I didn't understand. Please rephrase, e.g. \"Who is Amir Temur?\" or \"what can you do?\"."},
    "rude": {"uz": "Xatoim boʻlsa, uzr. Savolingizni boshqacha yozib koʻring, yaxshiroq javob berishga harakat qilaman.",
             "en": "Sorry if I got something wrong. Try rephrasing your question and I'll do my best."},
    "help": {"uz": f"Men **{NAME}**. Quyidagilarni qila olaman:\n\n"
                   "- 🌤 **Ob-havo** — «Samarqandda ob-havo qanday?»\n"
                   "- 💱 **Valyuta kursi** (MB) — «dollar kursi»\n"
                   "- 🧮 **Hisoblash** — «25 * 4 + 10»\n"
                   "- ⏰ **Eslatma** — «30 daqiqadan keyin eslat: choy»\n"
                   "- ✅ **Vazifalar** — «vazifa qoʻsh: bozorga borish»\n"
                   "- 🧠 **Xotira** — «eslab qol: ...» va «men haqimda nima bilasan?»\n"
                   "- 📰 **Yangiliklar** — «bugungi yangiliklar»\n"
                   "- 📚 **Savollarga javob** — Vikipediya asosida («Amir Temur kim?»)\n"
                   "- 📎 **Hujjatlar** — fayl yuklang, men undan qidirib javob beraman",
             "en": f"I'm **{NAME}**. I can help with weather, currency rates, calculations, reminders, to-do tasks, "
                   "memory, news, questions (from Wikipedia) and searching your uploaded documents."},
    "unknown": {"uz": "Bu haqda aniq maʼlumotim yoʻq. Bilmagan narsani toʻqib aytmayman.",
                "en": "I don't have reliable information about that, and I won't make something up."},
    "smalltalk": {"uz": "Rahmat, yaxshi. Sizda nima gaplar? Qanday yordam bera olaman?",
                  "en": "I'm fine, thank you. How can I help?"},
    "thanks": {"uz": "Arzimaydi. Yana savolingiz boʻlsa, bemalol.", "en": "You're welcome."},
    "bye": {"uz": "Xayr. Yaxshi kun tilayman.", "en": "Goodbye. Have a nice day."},
    "weather_need_city": {"uz": "Qaysi shahar uchun? Masalan: «Samarqandda ob-havo qanday?»",
                          "en": "Which city? For example: “weather in Samarkand”."},
    "task_need_text": {"uz": "Qanday vazifa qoʻshay? Masalan: «vazifa qoʻsh: ertaga bozorga borish».",
                       "en": "What task should I add?"},
    "reminder_need_time": {"uz": "Qachon eslatay? Masalan: «ertaga soat 9 da uchrashuvni eslat» yoki «30 daqiqadan keyin eslat».",
                           "en": "When should I remind you? E.g. “remind me in 30 minutes”."},
}


_QWORDS = re.compile(r"\b(kim|nima|qachon|qayer\w*|qanday|qancha|necha\w*|haqida|tushuntir\w*|nimaga|nega|bu|"
                     r"who|what|when|where|why|how|is|are|was|the|a|an|of|tell me about|explain)\b|[?.!,]", re.I)


def _online_lookup(text: str, terms: list[str], lang: str) -> dict | None:
    q = re.sub(r"\s+", " ", _QWORDS.sub(" ", text)).strip()
    if len(q) < 2:
        return None
    res = tools.wiki_lookup(q, "en" if lang == "en" else "uz")
    if "error" in res or not res.get("text"):
        return None
    if knowledge._title_overlap(terms, res["title"]) < 0.5 and _term_coverage(terms, res["text"][:400]) < 0.6:
        return None
    return res


def _term_coverage(terms: list[str], text: str) -> float:
    if not terms:
        return 0.0
    low = text.lower()
    return sum(t in low for t in terms) / len(terms)


def _best_passage(text: str, terms: list[str], max_chars: int = 600) -> str:
    paras = [p.strip() for p in text.split("\n") if len(p.strip()) > 20] or [text]
    best = max(paras, key=lambda p: _term_coverage(terms, p))
    return best[:max_chars] + ("…" if len(best) > max_chars else "")


def _first_sentences(text: str, n: int = 2, max_chars: int = 420) -> str:
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    first = next((p for p in paras if len(p) >= 60), paras[0] if paras else text)
    sents = re.split(r"(?<=[.!?])\s+", first)
    out = ""
    for s in sents[:n]:
        if len(out) + len(s) > max_chars and out:
            break
        out = f"{out} {s}".strip()
    return out


_FACT_RE = re.compile(
    r"(^|\s)(mening|menga tegishli|qo['ʻʼ’]?shnim\w*|kecha|bugun\w* (o['ʻʼ’]?yin|natija)\w*)(\s|$)|"
    r"\b(kim|qachon|qayer\w*|qaerda|necha|nechta|nechanchi|qancha|telefon\w*|manzil\w*|ismi|aholisi|"
    r"who|when|where|how many|how much)\b", re.I)


def _needs_facts(text: str) -> bool:
    return bool(_FACT_RE.search(text)) and not re.search(r"\b(nima uchun|nega|qanday qilib|why|how (do|does|can))\b", text, re.I)


GEN = {"temperature": 0.5, "top_k": 40, "top_p": 0.9, "repetition_penalty": 1.15}
STRICT_CONTEXT = True


class ChatModel:

    def __init__(self, ckpt: Path = CHAT_MODEL, tokenizer: Path = TOKENIZER):
        import torch

        from uzllm.model import GPT, GPTConfig
        from uzllm.tokenizer import load_tokenizer
        self.torch = torch
        ck = torch.load(ckpt, map_location="cpu", weights_only=False)
        self.model = GPT(GPTConfig(**ck["config"])).eval()
        self.model.load_state_dict(ck["model"])
        self.tok = load_tokenizer(tokenizer)
        self.end_id = self.tok.token_to_id("<|end|>")

    def prompt(self, history: list[dict], context: str | None) -> str:
        p = f"<|system|>{SYSTEM_PROMPT}<|end|>"
        for m in history[-3:]:
            role = "user" if m["role"] == "user" else "assistant"
            p += f"<|{role}|>{m['content']}<|end|>"
        if context:
            p += f"<|context|>{context}<|end|>"
        return p + "<|assistant|>"

    def stream(self, prompt: str, max_new_tokens: int = 300) -> Iterator[str]:
        torch = self.torch
        ids = self.tok.encode(prompt).ids[-(self.model.cfg.context_len - max_new_tokens):]
        idx = torch.tensor([ids])
        out_ids: list[int] = []
        printed = ""
        for nxt in self.model.generate_stream(idx, max_new_tokens, stop_ids={self.end_id}, **GEN):
            if nxt == self.end_id:
                break
            out_ids.append(nxt)
            text = self.tok.decode(out_ids)
            if not text.endswith("�"):
                yield text[len(printed):]
                printed = text


_chat_model: ChatModel | None = None
_chat_model_checked = False


def get_chat_model() -> ChatModel | None:
    global _chat_model, _chat_model_checked
    if not _chat_model_checked:
        _chat_model_checked = True
        if CHAT_MODEL.exists() and TOKENIZER.exists():
            try:
                _chat_model = ChatModel()
            except Exception as e:
                print("Chat-modelni yuklab bo'lmadi:", e)
    return _chat_model


def model_status() -> dict:
    m = get_chat_model()
    return {"name": NAME, "mode": "model" if m else "tools",
            "label": "OMZU-125M" if m else "Vositalar + bilim bazasi (model o'qitilmoqda)"}


def _stream_text(text: str, delay: float = 0.012) -> Iterator[dict]:
    for piece in re.findall(r"\S+\s*|\s+", text):
        yield {"type": "token", "text": piece}
        time.sleep(delay)


STATUS_TEXT = {
    "weather": ("Ob-havo tekshirilmoqda…", "Checking the weather…"),
    "currency": ("Markaziy bank kursi olinmoqda…", "Fetching exchange rate…"),
    "calculator": ("Hisoblanmoqda…", "Calculating…"),
    "add_reminder": ("Eslatma qoʻyilmoqda…", "Setting reminder…"),
    "list_reminders": ("Eslatmalar koʻrilmoqda…", "Reading reminders…"),
    "remember": ("Xotiraga yozilmoqda…", "Saving to memory…"),
    "list_memories": ("Xotira koʻrilmoqda…", "Reading memory…"),
    "now": ("Vaqt aniqlanmoqda…", "Checking time…"),
    "news": ("Yangiliklar yuklanmoqda…", "Loading news…"),
    "wiki_lookup": ("Internetdan qidirilmoqda…", "Searching the web…"),
    "add_task": ("Vazifa qoʻshilmoqda…", "Adding task…"),
    "list_tasks": ("Vazifalar koʻrilmoqda…", "Reading tasks…"),
    "complete_task": ("Belgilanmoqda…", "Marking done…"),
}


def respond(history: list[dict]) -> Iterator[dict]:
    raw = history[-1]["content"]
    if is_russian(raw) and not get_chat_model():
        yield {"type": "status", "text": "Поиск в Википедии…"}
        q = re.sub(r"\s+", " ", _RU_WORDS.sub(" ", re.sub(r"[?.!,]", " ", raw.lower()))).strip()
        res = tools.wiki_lookup(q or raw, "ru") if q else {"error": "empty"}
        if "error" not in res and res.get("text"):
            yield {"type": "sources", "items": [{"title": res["title"], "source": "wikipedia-online"}]}
            body = _first_sentences(res["text"], n=3, max_chars=600)
            yield from _stream_text(f"{body}\n\n*Источник: [{res['title']} — Википедия]({res['url']})*")
        else:
            yield from _stream_text("Извините, пока я хорошо понимаю только узбекский и английский. "
                                    "Русский язык появится в следующей версии.")
        yield {"type": "done"}
        return
    text = clean_uzbek(raw)
    lang = detect_lang(text)
    li = 0 if lang == "uz" else 1

    r = route(text)
    if r and "special" in r:
        yield from _stream_text(SPECIAL[r["special"]][lang])
        yield {"type": "done"}
        return
    if r and "tool" in r:
        yield {"type": "status", "text": STATUS_TEXT[r["tool"]][li]}
        res = tools.call_tool(r["tool"], r["args"])
        yield {"type": "tool", "name": r["tool"], "args": r["args"], "result": res}
        yield from _stream_text(compose_tool_answer(r["tool"], r["args"], res, lang))
        yield {"type": "done"}
        return

    yield {"type": "status", "text": "Bilim bazasidan qidirilmoqda…" if lang == "uz" else "Searching knowledge base…"}
    hits = knowledge.search(text, k=3)
    terms = knowledge._query_terms(text)
    model = get_chat_model()
    good = [h for h in hits if knowledge._title_overlap(terms, h["title"]) >= 0.5
            or (h["source"].startswith("user:") and _term_coverage(terms, h["text"]) >= 0.6)]
    is_question = "?" in text or bool(re.search(
        r"\b(kim|nima|qachon|qayer\w*|qanday|qancha|necha\w*|haqida|tushuntir\w*|nimaga|nega|who|what|when|where|why|how)\b",
        text.lower()))
    if not model and not is_question:
        good = []
    shown = good if not model else good + [h for h in hits if lang != "en" and h not in good and len(terms) >= 2 and _term_coverage(terms, h['title'] + ' ' + h['text']) >= 0.75]
    if not model and lang == "en" and is_question and terms:
        online = _online_lookup(text, terms, "en")
        if online:
            yield {"type": "sources", "items": [{"title": online["title"], "source": "wikipedia-online"}]}
            yield from _stream_text(compose_tool_answer("wiki_lookup", {}, online, "en"))
            yield {"type": "done"}
            return

    if shown:
        yield {"type": "sources", "items": [{"title": h["title"], "source": h["source"]} for h in shown]}

    if model and not shown and not is_question and len(text.split()) <= 3:
        yield from _stream_text(SPECIAL["unclear"][lang])
        yield {"type": "done"}
        return
    if model and STRICT_CONTEXT and not good and not any(len(terms) >= 2 and _term_coverage(terms, h['title'] + ' ' + h['text']) >= 0.75 for h in hits) and _needs_facts(text):
        yield from _stream_text(SPECIAL["unknown"][lang])
        yield {"type": "done"}
        return
    if model:
        ok_ids = {id(h) for h in good}
        extra = [h for h in hits if lang != "en" and id(h) not in ok_ids and len(terms) >= 2 and _term_coverage(terms, h['title'] + ' ' + h['text']) >= 0.75]
        used = (good + extra) if STRICT_CONTEXT else hits
        ctx = "\n\n".join(f"[{h['title']}] {h['text']}" for h in used) if used else None
        for piece in model.stream(model.prompt(history, ctx)):
            yield {"type": "token", "text": piece}
        yield {"type": "done"}
        return

    if good:
        h = good[0]
        is_user = h["source"].startswith("user:")
        body = _best_passage(h["text"], terms) if is_user else _first_sentences(h["text"])
        src_name = h["source"][5:] if is_user else "Vikipediya"
        if lang == "uz":
            ans = f"{body}\n\n*Manba: {src_name}" + ("" if is_user else f" — «{h['title']}»") + ".*"
        else:
            ans = (f"Here is what I found:\n\n{body}\n\n*Source: {src_name}" + ("" if is_user else f" — “{h['title']}”") + ".*")
        yield from _stream_text(ans)
    elif is_question and terms and (online := _online_lookup(text, terms, lang)):
        yield {"type": "status", "text": "Internetdan qidirilmoqda…" if lang == "uz" else "Searching the web…"}
        yield {"type": "sources", "items": [{"title": online["title"], "source": "wikipedia-online"}]}
        yield from _stream_text(compose_tool_answer("wiki_lookup", {}, online, lang))
    else:
        yield from _stream_text(
            "Bu haqda aniq maʼlumotim yoʻq.\n\n*Hozir men cheklangan rejimdaman: asosiy til modelim oʻqitilmoqda. "
            "Ob-havo, valyuta kursi, hisob-kitob, eslatmalar va Vikipediyadagi maʼlumotlar boʻyicha yordam bera olaman.*"
            if lang == "uz" else "I don't have reliable information about that yet — my language model is still training.")
    yield {"type": "done"}
