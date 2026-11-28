import json
import random
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uzllm.assistant import CREATOR, NAME, SYSTEM_PROMPT, compose_tool_answer
from uzllm.clean import clean_english, clean_uzbek
from uzllm.knowledge import KB_PATH

RAW = ROOT / "data" / "raw" / "sft"
OUT = ROOT / "data" / "sft"
rng = random.Random(42)

SYS = {"role": "system", "content": SYSTEM_PROMPT}


def dialog(*turns, src: str):
    return {"messages": [SYS, *turns], "src": src}


def U(t):
    return {"role": "user", "content": t}


def A(t):
    return {"role": "assistant", "content": t}


AYA_CAPS = {
    "Dolly-v2 (T)": 15_000, "Flan-CoT-submix (T)": 25_000, "NQ-Open (T)": 15_000, "HotpotQA (T)": 8_000,
    "Mintaka-inst (T)": 10_000, "PIQA (T)": 8_000, "Adversarial QA (T)": 6_000, "CNN-Daily-Mail (T)": 6_000,
    "Flan-GEM-wiki-lingua (T)": 5_000, "Flan-Coqa (T)": 4_000, "WIKI QA (T)": 2_000, "Joke-explaination-inst (T)": 1_000,
    "Flan-unified-QA (T)": 1_000, "SODA-inst (T)": 15_000, "Wiki-split-inst (T)": 2_000, "Xlel_wd-inst (T)": 2_000,
}


def aya_collection(limit: int = 130_000, per_source: int = 0):
    path = RAW / "aya_collection_language_split/northern_uzbek/train-00000-of-00001.parquet"
    if not path.exists():
        print("Aya Collection topilmadi:", path)
        return []
    counts: Counter = Counter()
    out = []
    pf = pq.ParquetFile(path)
    totals = Counter(pq.read_table(path, columns=["dataset_name"]).column("dataset_name").to_pylist())
    keep_p = {ds: min(1.0, 1.5 * AYA_CAPS.get(ds, 0) / n) for ds, n in totals.items()}
    rows = []
    for b in pf.iter_batches(batch_size=20_000, columns=["inputs", "targets", "dataset_name", "script"]):
        for r in zip(*(b.column(c).to_pylist() for c in ["inputs", "targets", "dataset_name", "script"])):
            if rng.random() < keep_p.get(r[2], 0):
                rows.append(r)
    rng.shuffle(rows)
    for inp, tgt, ds, script in rows:
        if len(out) >= limit:
            break
        if not inp or not tgt or "<unk>" in inp + tgt or (script and script != "Latn"):
            continue
        if len(inp) > 2400 or len(tgt) > 1500 or len(tgt.strip()) < 2:
            continue
        if counts[ds] >= AYA_CAPS.get(ds, 0):
            continue
        counts[ds] += 1
        out.append(dialog(U(clean_uzbek(inp)), A(clean_uzbek(tgt)), src=f"aya_col:{ds}"))
    print(f"Aya Collection: {len(out):,} ta ({len(counts)} manba)")
    return out


def aya_dataset():
    path = RAW / "aya_dataset/data/train-00000-of-00001.parquet"
    if not path.exists():
        print("Aya Dataset topilmadi:", path)
        return []
    t = pq.read_table(path, columns=["inputs", "targets", "language"]).to_pylist()
    uz = [r for r in t if "Uzbek" in (r["language"] or "")]
    en = [r for r in t if r["language"] == "English"]
    rng.shuffle(en)
    out = [dialog(U(clean_uzbek(r["inputs"])), A(clean_uzbek(r["targets"])), src="aya_ds:uz") for r in uz]
    out += [dialog(U(clean_english(r["inputs"])), A(clean_english(r["targets"])), src="aya_ds:en")
            for r in en[:12_000] if len(r["inputs"]) + len(r["targets"]) < 3000]
    print(f"Aya Dataset: {len(uz):,} o'zbekcha, {len(out) - len(uz):,} inglizcha")
    return out


PERSON_HINTS = re.compile(r"\b(tugʻilgan|shoir|yozuvchi|olim|hukmdor|siyosatchi|davlat arbobi|aktyor|aktrisa|"
                          r"futbolchi|xonanda|rassom|bastakor|faylasuf|sarkarda|podshoh|xon|amir|sulton)\b")
Q_TEMPLATES_PERSON = ["{t} kim?", "{t} haqida qisqacha maʼlumot bering.", "{t} kim boʻlgan?", "Menga {t} haqida aytib bering."]
Q_TEMPLATES_THING = ["{t} nima?", "{t} haqida qisqacha maʼlumot bering.", "{t} haqida nima bilasiz?", "Menga {t} haqida tushuntirib bering."]
DONT_KNOW = [
    "Kechirasiz, bu haqda aniq maʼlumotim yoʻq.",
    "Bu savol boʻyicha ishonchli maʼlumot topa olmadim.",
    "Aniq maʼlumotim yoʻq. Savolni boshqacha soʻrab koʻring.",
]


def _lead(text: str, n: int) -> str:
    sents = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    return " ".join(sents[:n]).strip()


def wiki_rag(n: int = 30_000):
    if not KB_PATH.exists():
        print("Bilim bazasi topilmadi — avval scripts/build_knowledge.py")
        return []
    con = sqlite3.connect(KB_PATH)
    rows = con.execute("SELECT title, text FROM chunks WHERE pos=0 AND length(text) > 250 "
                       "ORDER BY random() LIMIT ?", (int(n * 1.3),)).fetchall()
    con.close()
    out = []
    for i, (title, text) in enumerate(rows):
        if len(out) >= n or "(" in title and title.count("(") > 1:
            continue
        lead = _lead(text, rng.choice([1, 2, 2, 3]))
        if len(lead) < 60 or not lead.lower().startswith(title.split(" (")[0].lower()[:4]):
            continue
        tmpl = Q_TEMPLATES_PERSON if PERSON_HINTS.search(lead.lower()) else Q_TEMPLATES_THING
        q = rng.choice(tmpl).format(t=title.split(" (")[0])
        if rng.random() < 0.12:
            other_title, other_text = rows[(i + 7) % len(rows)]
            ctx = f"[{other_title}] {other_text}"
            out.append({"messages": [SYS, U(q), {"role": "context", "content": ctx}, A(rng.choice(DONT_KNOW))],
                        "src": "wiki:dontknow"})
        else:
            ctx = f"[{title}] {text}"
            out.append({"messages": [SYS, U(q), {"role": "context", "content": ctx}, A(lead)], "src": "wiki:rag"})
    print(f"Vikipediya RAG: {len(out):,}")
    return out


CITIES = ["Toshkent", "Samarqand", "Buxoro", "Xiva", "Fargʻona", "Andijon", "Namangan", "Qarshi", "Nukus",
          "Termiz", "Jizzax", "Navoiy", "Urganch", "Qoʻqon", "Guliston", "Moskva", "Istanbul", "London", "Dubay", "Seul"]
SKIES = ["ochiq osmon", "asosan ochiq", "qisman bulutli", "bulutli", "yengil yomgʻir", "yomgʻir", "qor", "tuman"]
CURR = [("USD", "AQSH dollari", ["dollar", "dollar", "USD"], 11900, 12900), ("EUR", "EVRO", ["yevro", "evro"], 12800, 14300),
        ("RUB", "Rossiya rubli", ["rubl"], 120, 160), ("KZT", "Qozogʻiston tengesi", ["tenge"], 22, 28)]


def fake_weather(city, days):
    t = rng.uniform(-8, 38)
    fc = [{"date": f"2026-11-{20 + d:02d}", "min_c": round(t - rng.uniform(4, 10), 1), "max_c": round(t + rng.uniform(0, 5), 1),
           "sky": rng.choice(SKIES), "rain_chance": rng.randint(0, 95)} for d in range(days)]
    return {"city": city, "country": "Uzbekistan", "now": {"temp_c": round(t, 1), "feels_like_c": round(t - rng.uniform(0, 3), 1),
            "humidity": rng.randint(20, 95), "wind_kmh": round(rng.uniform(1, 25), 1), "sky": rng.choice(SKIES)}, "forecast": fc}


def tool_examples(n: int = 8_000):
    out = []
    for _ in range(n):
        kind = rng.choice(["weather", "weather", "currency", "currency", "calculator", "reminder", "remember", "now"])
        if kind == "weather":
            city = rng.choice(CITIES)
            days = rng.choice([1, 1, 2, 7])
            q = rng.choice([f"{city}da ob-havo qanday?", f"{city}da {'ertaga ' if days == 2 else ''}havo qanday boʻladi?",
                            f"{city} ob-havosi", f"{city}da haftalik ob-havo" if days == 7 else f"Hozir {city}da necha daraja?"])
            args = {"city": city, "days": days}
            res = fake_weather(city, days)
        elif kind == "currency":
            code, name, words, lo, hi = rng.choice(CURR)
            amount = rng.choice([1, 1, 50, 100, 250, 1000])
            w = rng.choice(words)
            q = rng.choice([f"{w} kursi qancha?", f"Bugun {w} necha soʻm?"] if amount == 1 else
                           [f"{amount} {w} necha soʻm?", f"{amount} {w} qancha boʻladi?"])
            rate = round(rng.uniform(lo, hi), 2)
            args = {"code": code, "amount": float(amount)}
            res = {"currency": code, "name": name, "rate_uzs": rate, "change": round(rng.uniform(-40, 40), 2),
                   "date": "20.11.2026", "amount": float(amount), "total_uzs": round(rate * amount, 2)}
        elif kind == "calculator":
            a, b = rng.randint(2, 999), rng.randint(2, 99)
            op = rng.choice(["+", "-", "*", "/"])
            expr = f"{a}{op}{b}"
            q = rng.choice([f"{a} {op} {b} necha boʻladi?", f"Hisobla: {expr}", f"{expr} = ?"])
            val = eval(expr)
            args = {"expression": expr}
            res = {"expression": expr, "result": int(val) if float(val).is_integer() else round(val, 6)}
        elif kind == "reminder":
            what = rng.choice(["uchrashuv", "dori ichish", "onamga qoʻngʻiroq qilish", "darsga borish", "choy", "sport zal"])
            hh = rng.randint(6, 22)
            q = f"Ertaga soat {hh} da {what}ni eslatib qoʻying"
            args = {"text": what, "when": f"ertaga {hh:02d}:00"}
            res = {"id": rng.randint(1, 99), "text": what, "due": f"2026-11-21 {hh:02d}:00"}
            kind = "add_reminder"
        elif kind == "remember":
            fact = rng.choice(["Mening tugʻilgan kunim 5-may", "Men dasturchiman", "Sevimli rangim — koʻk",
                               "Ukamning ismi Jasur", "Men Samarqandda yashayman"])
            q = f"Eslab qol: {fact}"
            args = {"fact": fact}
            res = {"id": rng.randint(1, 99), "saved": fact}
        else:
            q = rng.choice(["Soat necha boʻldi?", "Bugun qaysi kun?", "Bugungi sana qanday?"])
            args = {}
            res = {"date": "2026-yil 20-noyabr", "weekday": "juma", "time": f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}"}
        tool = kind if kind not in ("reminder",) else "add_reminder"
        tool = {"now": "now", "remember": "remember"}.get(tool, tool)
        answer = compose_tool_answer(tool, args, res, "uz")
        out.append({"messages": [SYS, U(q), {"role": "tool_call", "content": {"name": tool, "args": args}},
                                 {"role": "tool_result", "content": res}, A(answer)], "src": f"tool:{tool}"})
    print(f"Vositalar: {len(out):,}")
    return out


def persona():
    ident_q = ["Sen kimsan?", "Siz kimsiz?", "Isming nima?", "Ismingiz nima?", "Seni kim yaratgan?", "Sizni kim yaratgan?",
               "Kim tomonidan yaratilgansiz?", "Sen ChatGPTmisan?", "Sen qaysi kompaniyaning modelisan?", "Oʻzing haqingda gapirib ber"]
    ident_a = [f"Men {NAME} — sunʼiy intellekt yordamchisiman. Meni {CREATOR} noldan yaratgan.",
               f"Mening ismim {NAME}. Meni {CREATOR} yaratgan. Savollaringizga javob beraman va kundalik ishlarda yordam beraman.",
               f"Men {NAME}man — {CREATOR} tomonidan noldan oʻqitilgan til modeli. ChatGPT ham, boshqa kompaniyaning modeli ham emasman."]
    en_q = ["Who are you?", "What is your name?", "Who created you?", "Are you ChatGPT?"]
    en_a = [f"I'm {NAME}, an AI assistant built from scratch by {CREATOR}.",
            f"My name is {NAME}. I was created by {CREATOR}. I'm not ChatGPT."]
    small = [
        ("Salom", "Assalomu alaykum. Sizga qanday yordam bera olaman?"),
        ("Assalomu alaykum", "Vaalaykum assalom. Qanday yordam kerak?"),
        ("Qalaysiz?", "Rahmat, yaxshi. Sizga qanday yordam bera olaman?"),
        ("Rahmat", "Arzimaydi. Yana savolingiz boʻlsa, bemalol."),
        ("Katta rahmat, yordam berding", "Arzimaydi. Doim xizmatingizdaman."),
        ("Xayr", "Xayr. Yaxshi kun tilayman."),
        ("Hello", "Hello. How can I help you?"),
        ("Thanks!", "You're welcome."),
    ]
    out = []
    for _ in range(25):
        out += [dialog(U(q), A(rng.choice(ident_a)), src="persona") for q in ident_q]
        out += [dialog(U(q), A(rng.choice(en_a)), src="persona") for q in en_q]
        out += [dialog(U(q), A(a), src="persona") for q, a in small]
    print(f"Shaxsiyat: {len(out):,}")
    return out


def teacher():
    import glob

    from teacher_filter import load
    paths = sorted(glob.glob(str(ROOT / "data" / "teacher" / "out*.jsonl")))
    if not paths:
        return []
    st = Counter()
    pairs = load(paths, st)
    print(f"Ustoz: {len(pairs):,} juftlik  {dict(st)}")
    return [dialog(U(p["q"]), A(p["a"]), src=f"teacher:{p['kind']}") for p in pairs]


def oasst_english(limit: int = 12_000):
    path = ROOT / "data" / "teacher" / "oasst2_train.jsonl"
    if not path.exists():
        return []
    msgs = {}
    kids: dict = {}
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        if r["lang"] != "en" or r["deleted"] or r.get("review_result") is False:
            continue
        msgs[r["message_id"]] = r
        kids.setdefault(r["parent_id"], []).append(r["message_id"])
    out = []
    for root in kids.get(None, []):
        turns, cur = [], root
        while cur and len(turns) < 6:
            m = msgs[cur]
            turns.append(U(clean_english(m["text"])) if m["role"] == "prompter" else A(clean_english(m["text"])))
            ch = [c for c in kids.get(cur, []) if c in msgs]
            ch.sort(key=lambda c: (msgs[c].get("rank") is None, msgs[c].get("rank") or 0))
            cur = ch[0] if ch else None
        if len(turns) >= 2 and turns[-1]["role"] == "user":
            turns = turns[:-1]
        if len(turns) >= 2 and sum(len(t["content"]) for t in turns) < 6000:
            out.append(dialog(*turns, src="oasst:en"))
    rng.shuffle(out)
    return out[:limit]


def main():
    data = (aya_collection() + aya_dataset() + wiki_rag() + tool_examples() + persona()
            + teacher() + oasst_english())
    rng.shuffle(data)
    OUT.mkdir(parents=True, exist_ok=True)
    n_val = min(2000, len(data) // 50)
    for name, part in [("val", data[:n_val]), ("train", data[n_val:])]:
        with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for d in part:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"Jami: {len(data):,} -> {OUT}")
    print(Counter(d["src"].split(":")[0] for d in data))


if __name__ == "__main__":
    main()
