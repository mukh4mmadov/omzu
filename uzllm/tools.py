import ast
import json
import math
import operator
import re
import sqlite3
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "assistant.db"
HTTP_TIMEOUT = 10
USER_AGENT = "uzllm-assistant/0.1"


_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "sin": math.sin, "cos": math.cos,
    "tan": math.tan, "log": math.log, "log10": math.log10, "exp": math.exp,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("daraja juda katta")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    raise ValueError("ruxsat etilmagan ifoda")


def calculator(expression: str) -> dict:
    expr = expression.replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", ".")
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*(?:of|dan)?\s*(\d+(?:\.\d+)?)", r"(\2*\1/100)", expr)
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expr)
    try:
        value = _eval(ast.parse(expr, mode="eval"))
    except ZeroDivisionError:
        return {"error": "nolga bo'lish mumkin emas"}
    except Exception as e:
        return {"error": f"hisoblab bo'lmadi: {e}"}
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    elif isinstance(value, float):
        value = round(value, 6)
    return {"expression": expression, "result": value}


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


WEATHER_CODES = {
    0: "ochiq osmon", 1: "asosan ochiq", 2: "qisman bulutli", 3: "bulutli",
    45: "tuman", 48: "qirov bilan tuman", 51: "yengil mayda yomg'ir", 53: "mayda yomg'ir",
    55: "kuchli mayda yomg'ir", 61: "yengil yomg'ir", 63: "yomg'ir", 65: "kuchli yomg'ir",
    66: "muzli yomg'ir", 67: "kuchli muzli yomg'ir", 71: "yengil qor", 73: "qor", 75: "kuchli qor",
    77: "qor donachalari", 80: "yengil jala", 81: "jala", 82: "kuchli jala",
    85: "qor yog'ishi", 86: "kuchli qor yog'ishi", 95: "momaqaldiroq",
    96: "do'l bilan momaqaldiroq", 99: "kuchli do'l bilan momaqaldiroq",
}


CITY_ALIASES = {
    "toshkent": "Tashkent", "samarqand": "Samarkand", "buxoro": "Bukhara", "xiva": "Khiva",
    "fargʻona": "Fergana", "andijon": "Andijan", "namangan": "Namangan", "qarshi": "Karshi",
    "nukus": "Nukus", "jizzax": "Jizzakh", "guliston": "Gulistan", "termiz": "Termez",
    "navoiy": "Navoiy", "urganch": "Urgench", "qoʻqon": "Kokand", "margʻilon": "Margilan",
    "chirchiq": "Chirchiq", "olmaliq": "Almalyk", "angren": "Angren", "shahrisabz": "Shahrisabz",
    "denov": "Denov", "kattaqoʻrgʻon": "Kattakurgan", "zarafshon": "Zarafshan", "moskva": "Moscow",
    "londonda": "London", "parij": "Paris", "istanbul": "Istanbul", "dubay": "Dubai", "seul": "Seoul",
    "pekin": "Beijing", "nyu-york": "New York", "berlin": "Berlin", "olmaota": "Almaty",
    "bishkek": "Bishkek", "dushanbe": "Dushanbe", "ashxobod": "Ashgabat",
}


def _city_query(city: str) -> str:
    key = city.lower().replace("'", "ʻ").replace("‘", "ʻ")
    if key in CITY_ALIASES:
        return CITY_ALIASES[key]
    q = key.replace("oʻ", "o").replace("gʻ", "g").replace("ʼ", "")
    return q[:1].upper() + q[1:]


def weather(city: str, days: int = 1) -> dict:
    days = max(1, min(7, int(days)))
    try:
        results = []
        for name in dict.fromkeys([_city_query(city), city]):
            q = urllib.parse.urlencode({"name": name, "count": 5, "language": "en", "format": "json"})
            results = _get_json(f"https://geocoding-api.open-meteo.com/v1/search?{q}").get("results") or []
            if results:
                break
        if not results:
            return {"error": f"'{city}' shahri topilmadi"}
        g = max(results, key=lambda r: r.get("population") or 0)
        params = urllib.parse.urlencode({
            "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto",
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": days,
        })
        w = _get_json(f"https://api.open-meteo.com/v1/forecast?{params}")
    except Exception as e:
        return {"error": f"ob-havo xizmatiga ulanib bo'lmadi: {e}"}
    cur = w["current"]
    d = w["daily"]
    shown = city[:1].upper() + city[1:] if city.lower().replace("'", "ʻ") in CITY_ALIASES else g["name"]
    country = {"Uzbekistan": "Oʻzbekiston", "Russia": "Rossiya", "Kazakhstan": "Qozogʻiston", "Turkey": "Turkiya",
               "United Kingdom": "Buyuk Britaniya", "United Arab Emirates": "BAA", "South Korea": "Janubiy Koreya",
               "Kyrgyzstan": "Qirgʻiziston", "Tajikistan": "Tojikiston", "Turkmenistan": "Turkmaniston",
               "Germany": "Germaniya", "France": "Fransiya", "China": "Xitoy", "United States": "AQSH"}.get(
        g.get("country", ""), g.get("country", ""))
    return {
        "city": shown, "country": country,
        "now": {
            "temp_c": cur["temperature_2m"], "feels_like_c": cur["apparent_temperature"],
            "humidity": cur["relative_humidity_2m"], "wind_kmh": cur["wind_speed_10m"],
            "sky": WEATHER_CODES.get(cur["weather_code"], "noma'lum"),
        },
        "forecast": [
            {"date": d["time"][i], "min_c": d["temperature_2m_min"][i], "max_c": d["temperature_2m_max"][i],
             "sky": WEATHER_CODES.get(d["weather_code"][i], "noma'lum"),
             "rain_chance": d["precipitation_probability_max"][i]}
            for i in range(len(d["time"]))
        ],
    }


def currency(code: str = "USD", amount: float = 1.0) -> dict:
    code = code.upper().strip()
    try:
        rows = _get_json(f"https://cbu.uz/uz/arkhiv-kursov-valyut/json/{urllib.parse.quote(code)}/")
    except Exception as e:
        return {"error": f"Markaziy bank saytiga ulanib bo'lmadi: {e}"}
    if not rows:
        return {"error": f"'{code}' valyutasi topilmadi"}
    r = rows[0]
    rate = float(r["Rate"]) / float(r.get("Nominal", 1) or 1)
    return {
        "currency": code, "name": r.get("CcyNm_UZ", code), "rate_uzs": rate,
        "change": float(r.get("Diff", 0)), "date": r.get("Date"),
        "amount": amount, "total_uzs": round(rate * float(amount), 2),
    }


NEWS_FEEDS = {
    "Kun.uz": "https://kun.uz/news/rss",
    "Gazeta.uz": "https://www.gazeta.uz/uz/rss/",
    "Spot.uz": "https://www.spot.uz/oz/rss/",
    "UzA": "https://uza.uz/uz/rss",
    "Daryo.uz": "https://daryo.uz/feed",
}
_news_cache: dict = {"t": 0.0, "items": []}


def _fix_latin(s: str) -> str:
    from uzllm.clean import clean_uzbek
    for a, b in (("ö", "oʻ"), ("Ö", "Oʻ"), ("ğ", "gʻ"), ("Ğ", "Gʻ"), ("ş", "sh"), ("Ş", "Sh"), ("ç", "ch"), ("Ç", "Ch")):
        s = s.replace(a, b)
    return clean_uzbek(s)


def _fetch_feed(name: str, url: str) -> list[dict]:
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            root = ET.fromstring(r.read())
    except Exception:
        return []
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate") or "").timestamp()
        except Exception:
            ts = 0.0
        items.append({"title": _fix_latin(title), "link": link, "source": name, "ts": ts})
    return items


def news(limit: int = 8, source: str | None = None) -> dict:
    import time as _time
    from concurrent.futures import ThreadPoolExecutor
    if _time.time() - _news_cache["t"] > 600 or not _news_cache["items"]:
        with ThreadPoolExecutor(max_workers=len(NEWS_FEEDS)) as ex:
            results = list(ex.map(lambda kv: _fetch_feed(*kv), NEWS_FEEDS.items()))
        items = [i for r in results for i in r]
        if items:
            items.sort(key=lambda i: -i["ts"])
            _news_cache.update(t=_time.time(), items=items)
    items = [i for i in _news_cache["items"]
             if not re.search(r"falsafa doktori|fan doktori|dissertatsiya|ilmiy daraja", i["title"], re.I)]
    if source:
        items = [i for i in items if source.lower() in i["source"].lower()]
    if not items:
        return {"error": "yangiliklar saytlariga ulanib bo'lmadi"}
    by_src: dict[str, list] = {}
    for i in items:
        by_src.setdefault(i["source"], []).append(i)
    mixed = []
    while any(by_src.values()):
        for src in list(by_src):
            if by_src[src]:
                mixed.append(by_src[src].pop(0))
    items = mixed
    out = []
    for i in items[: max(1, min(20, int(limit)))]:
        t = datetime.fromtimestamp(i["ts"]).strftime("%H:%M, %d.%m") if i["ts"] else ""
        out.append({"title": i["title"], "link": i["link"], "source": i["source"], "time": t})
    return {"items": out}


def wiki_lookup(query: str, lang: str = "uz") -> dict:
    lang = lang if re.fullmatch(r"[a-z]{2,3}", lang or "") else "uz"
    base = f"https://{lang}.wikipedia.org/w/api.php"
    try:
        s = _get_json(base + "?" + urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": query, "srlimit": 1, "format": "json"}))
        hits = s.get("query", {}).get("search", [])
        if not hits:
            return {"error": f"Vikipediyada '{query}' topilmadi"}
        title = hits[0]["title"]
        e = _get_json(base + "?" + urllib.parse.urlencode({
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "redirects": 1,
            "titles": title, "format": "json"}))
        page = next(iter(e["query"]["pages"].values()))
    except Exception as ex:
        return {"error": f"Vikipediyaga ulanib bo'lmadi: {ex}"}
    text = (page.get("extract") or "").strip()
    return {"title": page.get("title", title), "lang": lang, "text": text[:1500],
            "url": f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(page.get("title", title).replace(" ", "_"))}


@contextmanager
def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY, text TEXT NOT NULL, due TEXT NOT NULL,
            created TEXT NOT NULL, done INTEGER DEFAULT 0)""")
        con.execute("""CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY, fact TEXT NOT NULL, created TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY, text TEXT NOT NULL, due TEXT, done INTEGER DEFAULT 0,
            created TEXT NOT NULL, done_at TEXT)""")
        yield con
        con.commit()
    finally:
        con.close()


def _parse_when(when: str, now: datetime) -> datetime | None:
    s = when.strip().lower()
    m = re.fullmatch(r"(\d+)\s*(daqiqa|min|minut|soat|hour|kun|day)\w*", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"daqiqa": timedelta(minutes=n), "min": timedelta(minutes=n), "minut": timedelta(minutes=n),
                 "soat": timedelta(hours=n), "hour": timedelta(hours=n),
                 "kun": timedelta(days=n), "day": timedelta(days=n)}[unit]
        return now + delta
    day = now.date()
    if s.startswith("ertaga"):
        day += timedelta(days=1)
        s = s.removeprefix("ertaga").strip()
    elif s.startswith("indinga"):
        day += timedelta(days=2)
        s = s.removeprefix("indinga").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", s)
    if m:
        t = datetime.combine(day, datetime.min.time()).replace(hour=int(m.group(1)), minute=int(m.group(2)))
        if t <= now and day == now.date():
            t += timedelta(days=1)
        return t
    return None


def add_reminder(text: str, when: str) -> dict:
    now = datetime.now()
    due = _parse_when(when, now)
    if due is None:
        return {"error": f"vaqtni tushunmadim: '{when}'"}
    with _db() as con:
        cur = con.execute("INSERT INTO reminders(text, due, created) VALUES (?,?,?)",
                          (text, due.isoformat(timespec="minutes"), now.isoformat(timespec="seconds")))
    return {"id": cur.lastrowid, "text": text, "due": due.strftime("%Y-%m-%d %H:%M")}


def list_reminders(include_done: bool = False) -> dict:
    with _db() as con:
        q = "SELECT id, text, due, done FROM reminders" + ("" if include_done else " WHERE done=0") + " ORDER BY due"
        rows = con.execute(q).fetchall()
    return {"reminders": [{"id": r[0], "text": r[1], "due": r[2].replace("T", " "), "done": bool(r[3])} for r in rows]}


def due_reminders() -> list[dict]:
    now = datetime.now().isoformat(timespec="minutes")
    with _db() as con:
        rows = con.execute("SELECT id, text, due FROM reminders WHERE done=0 AND due<=?", (now,)).fetchall()
        con.executemany("UPDATE reminders SET done=1 WHERE id=?", [(r[0],) for r in rows])
    return [{"id": r[0], "text": r[1], "due": r[2].replace("T", " ")} for r in rows]


def delete_reminder(id: int) -> dict:
    with _db() as con:
        n = con.execute("DELETE FROM reminders WHERE id=?", (int(id),)).rowcount
    return {"deleted": bool(n)}


def remember(fact: str) -> dict:
    with _db() as con:
        cur = con.execute("INSERT INTO memories(fact, created) VALUES (?,?)",
                          (fact.strip(), datetime.now().isoformat(timespec="seconds")))
    return {"id": cur.lastrowid, "saved": fact.strip()}


def list_memories() -> dict:
    with _db() as con:
        rows = con.execute("SELECT id, fact, created FROM memories ORDER BY id").fetchall()
    return {"memories": [{"id": r[0], "fact": r[1], "created": r[2][:10]} for r in rows]}


def forget(id: int) -> dict:
    with _db() as con:
        n = con.execute("DELETE FROM memories WHERE id=?", (int(id),)).rowcount
    return {"deleted": bool(n)}


def _due_date(when: str | None) -> str | None:
    if not when:
        return None
    s = when.strip().lower()
    today = datetime.now().date()
    if s in ("bugun", "today"):
        return today.isoformat()
    if s in ("ertaga", "tomorrow"):
        return (today + timedelta(days=1)).isoformat()
    if s in ("indinga",):
        return (today + timedelta(days=2)).isoformat()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m"):
        try:
            d = datetime.strptime(s, fmt).date()
            return (d.replace(year=today.year) if fmt == "%d.%m" else d).isoformat()
        except ValueError:
            pass
    return None


def add_task(text: str, due: str | None = None) -> dict:
    text = text.strip(" .,:;")
    if not text:
        return {"error": "vazifa matni bo'sh"}
    d = _due_date(due)
    with _db() as con:
        cur = con.execute("INSERT INTO tasks(text, due, created) VALUES (?,?,?)",
                          (text, d, datetime.now().isoformat(timespec="seconds")))
    return {"id": cur.lastrowid, "text": text, "due": d}


def list_tasks(include_done: bool = False) -> dict:
    with _db() as con:
        q = "SELECT id, text, due, done FROM tasks" + ("" if include_done else " WHERE done=0") + \
            " ORDER BY done, due IS NULL, due, id"
        rows = con.execute(q).fetchall()
    return {"tasks": [{"id": r[0], "text": r[1], "due": r[2], "done": bool(r[3])} for r in rows]}


def complete_task(id: int | None = None, text: str | None = None, done: bool = True) -> dict:
    with _db() as con:
        row = None
        if id is not None:
            row = con.execute("SELECT id, text FROM tasks WHERE id=?", (int(id),)).fetchone()
        elif text:
            words = [w for w in re.findall(r"[\wʻʼ]+", text.lower()) if len(w) > 2]
            best, best_score = None, 0
            for r in con.execute("SELECT id, text FROM tasks WHERE done=?", (0 if done else 1,)).fetchall():
                score = sum(w[: max(4, len(w) - 3)] in r[1].lower() for w in words)
                if score > best_score:
                    best, best_score = r, score
            row = best
        if not row:
            return {"error": "bunday vazifa topilmadi"}
        con.execute("UPDATE tasks SET done=?, done_at=? WHERE id=?",
                    (1 if done else 0, datetime.now().isoformat(timespec="seconds") if done else None, row[0]))
    return {"id": row[0], "text": row[1], "done": done}


def delete_task(id: int) -> dict:
    with _db() as con:
        n = con.execute("DELETE FROM tasks WHERE id=?", (int(id),)).rowcount
    return {"deleted": bool(n)}


def now_info() -> dict:
    n = datetime.now()
    oylar = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
             "sentabr", "oktabr", "noyabr", "dekabr"]
    kunlar = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]
    return {"date": f"{n.year}-yil {n.day}-{oylar[n.month - 1]}", "weekday": kunlar[n.weekday()],
            "time": n.strftime("%H:%M")}


TOOLS = {
    "calculator": calculator,
    "weather": weather,
    "currency": currency,
    "add_reminder": add_reminder,
    "list_reminders": list_reminders,
    "delete_reminder": delete_reminder,
    "remember": remember,
    "list_memories": list_memories,
    "forget": forget,
    "now": now_info,
    "news": news,
    "wiki_lookup": wiki_lookup,
    "add_task": add_task,
    "list_tasks": list_tasks,
    "complete_task": complete_task,
    "delete_task": delete_task,
}


def call_tool(name: str, args: dict | None = None) -> dict:
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"bunday vosita yo'q: {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"error": f"noto'g'ri argumentlar: {e}"}
