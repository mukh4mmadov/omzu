import json
import random
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "teacher" / "prompts.jsonl"
N_WIKI, N_TOPIC_WIKI, N_OASST = 15000, 2500, 15000
random.seed(7)

SYSTEM = (
    "You are an expert Uzbek writer creating training data for an Uzbek AI assistant named OMZU. "
    "Write ONLY in Uzbek, Latin script, modern official orthography: use oʻ and gʻ (with the ʻ sign), "
    "sh, ch, ng, and ʼ for the tutuq belgisi. Never use Cyrillic letters. Never use Turkish, Kazakh, "
    "Russian or English words when a normal Uzbek word exists. The assistant addresses the user "
    "politely with 'siz', is serious, clear and accurate. Never invent facts, numbers or dates; "
    "if something is uncertain, the answer must honestly say so. Output valid JSON only, no extra text."
)

WIKI_TMPL = (
    "Below is a passage from Uzbek Wikipedia.\n\nTitle: {title}\nPassage: {text}\n\n"
    "Create 3 question–answer pairs that a curious person might ask an assistant, answerable from the "
    "passage. At least one must be a 'nima uchun' (why) or 'qanday qilib' (how) question that needs an "
    "explanation. Questions should sound like real users (short, natural). Answers: 2–5 sentences, "
    "self-contained, do NOT mention 'the passage' or 'the text'. Use only facts from the passage.\n"
    'Output JSON: [{{"q": "...", "a": "..."}}, ...]'
)

TOPIC_TMPL = (
    "Topic: {topic}\n\n"
    "Write 5 diverse questions in Uzbek that people in Uzbekistan might really ask an AI assistant about "
    "this topic. Mix the types: 'nima uchun' (why), 'qanday qilib' (how), 'nima' (what is), practical "
    "advice, and comparison. Then answer each one well: a clear explanation in 3–8 sentences, or a short "
    "list when helpful. Keep facts general and correct; for health, law or money add a short note to "
    "consult a specialist when appropriate.\n"
    'Output JSON: [{{"q": "...", "a": "..."}}, ...]'
)

OASST_TMPL = (
    "User request (English):\n{text}\n\n"
    "1) Translate the request into natural Uzbek as a real Uzbek user would write it. "
    "2) Write the assistant's helpful answer in Uzbek. Keep code, formulas and English examples "
    "unchanged when they must stay in English. If the request asks about something specific to "
    "another country, answer it as asked. If the request is harmful, politely refuse in Uzbek.\n"
    'Output JSON: {{"q": "...", "a": "..."}}'
)

TOPICS = """
sogʻlom ovqatlanish; uyqu va dam olish; sport va jismoniy mashqlar; shamollash va gripp; bosh ogʻrigʻi;
qon bosimi; qandli diabet; tish salomatligi; koʻz salomatligi; stress va asab; bolalar tarbiyasi;
chaqaloq parvarishi; maktab va oʻqish; oliy taʼlim va universitetga kirish; ingliz tilini oʻrganish;
kitob oʻqish odati; vaqtni boshqarish; ish topish va rezyume yozish; suhbatdan (intervyudan) oʻtish;
kichik biznes ochish; shaxsiy byudjet; jamgʻarma va omonat; kredit va qarz; inflyatsiya; valyuta kursi;
soliqlar haqida umumiy; internet xavfsizligi; parol va akkaunt himoyasi; smartfon tanlash;
kompyuter tezligi; dasturlashni oʻrganish; Python dasturlash; veb-sayt yaratish; sunʼiy intellekt;
ijtimoiy tarmoqlar; onlayn xaridlar; plov tayyorlash; non yopish; somsa; manti; choy madaniyati;
mehmon kutish; toʻy marosimlari; Navroʻz; Ramazon va roʻza; hayit; qoʻshnichilik; oila munosabatlari;
doʻstlik; muloqot madaniyati; nutq va notiqlik; ishonch va motivatsiya; odatlarni oʻzgartirish;
avtomobil haydash; avtomobilga qarash; yoʻl harakati qoidalari; jamoat transporti; sayohat rejalash;
Samarqand; Buxoro; Xiva; Toshkent; Fargʻona vodiysi; Orol dengizi; ob-havo va iqlim; yomgʻir va qor;
chaqmoq va momaqaldiroq; quyosh tizimi; oy va uning fazalari; yulduzlar; osmon nima uchun koʻk;
kamalak; suvning aylanishi; zilzila; vulqonlar; okeanlar; oʻsimliklar fotosintezi; hayvonlar;
uy hayvonlari parvarishi; mushuk; it; qushlar; asalarichilik; dehqonchilik; paxta; bogʻdorchilik;
pomidor yetishtirish; uzum; olma daraxti; suvni tejash; elektr energiyasini tejash; quyosh panellari;
iqlim oʻzgarishi; chiqindilarni qayta ishlash; havo ifloslanishi; inson tanasi; yurak qanday ishlaydi;
miya; qon guruhlari; immunitet; vitaminlar; vaksinalar; antibiotiklar; birinchi tibbiy yordam;
kuyish; suyak sinishi; issiq urishi; matematika; foizlarni hisoblash; kasrlar; geometriya;
fizika qonunlari; tortishish kuchi; elektr toki; magnit; tovush; yorugʻlik; kimyo; atomlar;
Amir Temur; Alisher Navoiy; Mirzo Ulugʻbek; Ibn Sino; Al-Xorazmiy; Bobur; Jadidlar; Ipak yoʻli;
Oʻzbekiston mustaqilligi; Oʻzbekiston geografiyasi; Oʻzbekiston Konstitutsiyasi; fuqarolarning huquqlari;
mehnat huquqlari; isteʼmolchi huquqlari; pasport va hujjatlar; uy-joy ijarasi; uy sotib olish;
taʼmirlash ishlari; uyni tozalash; kir yuvish; dazmollash; bogʻcha tanlash; oʻsmirlar bilan muloqot;
qariyalarga gʻamxoʻrlik; xotira va eslab qolish; imtihonga tayyorlanish; diqqatni jamlash;
ijodkorlik; rasm chizish; musiqa; dutor va rubob; shaxmat; futbol; kurash; boks; yugurish;
suzish; velosiped; yoga; vazn tashlash; mushak yigʻish; suv ichish; nonushta; kofe; shakar zarari;
tuz; fast fud; meva va sabzavotlar; sut mahsulotlari; goʻsht; baliq; non; guruch; qovun va tarvuz
"""


def topics() -> list[str]:
    return [t.strip() for t in TOPICS.replace("\n", " ").split(";") if t.strip()]


def wiki_rows(db: sqlite3.Connection) -> tuple[list, list]:
    rows = db.execute(
        "select title, text, pos from chunks where length(text) between 450 and 1600 "
        "and title not like '%(%' order by random() limit ?", (N_WIKI * 2,)).fetchall()
    out, seen = [], set()
    for title, text, pos in rows:
        if title in seen or sum(ch.isdigit() for ch in text) > len(text) * 0.08:
            continue
        seen.add(title)
        out.append((title, text))
        if len(out) >= N_WIKI:
            break
    heads = db.execute(
        "select title from chunks where pos=0 and length(text) > 900 and title not like '%(%' "
        "order by random() limit ?", (N_TOPIC_WIKI,)).fetchall()
    return out, [h[0] for h in heads]


def oasst_prompts() -> list[str]:
    path = ROOT / "data" / "teacher" / "oasst2_train.jsonl"
    out = []
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        if (r["parent_id"] is None and r["role"] == "prompter" and r["lang"] == "en"
                and not r["deleted"] and r.get("review_result") is not False and 15 < len(r["text"]) < 1500):
            out.append(r["text"].strip())
    random.shuffle(out)
    return out[:N_OASST]


def main():
    db = sqlite3.connect(ROOT / "data" / "knowledge.db")
    wikis, heads = wiki_rows(db)
    tops = topics() * 4 + heads
    oas = oasst_prompts()
    items = []
    for i, (title, text) in enumerate(wikis):
        items.append({"id": f"w{i}", "kind": "wiki", "prompt": WIKI_TMPL.format(title=title, text=text)})
    for i, t in enumerate(tops):
        items.append({"id": f"t{i}", "kind": "topic", "prompt": TOPIC_TMPL.format(topic=t)})
    for i, t in enumerate(oas):
        items.append({"id": f"o{i}", "kind": "oasst", "prompt": OASST_TMPL.format(text=t)})
    random.shuffle(items)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for it in items:
            it["system"] = SYSTEM
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    kinds = {k: sum(1 for x in items if x["kind"] == k) for k in ("wiki", "topic", "oasst")}
    print(f"{len(items)} ta topshiriq -> {OUT}  {kinds}")


if __name__ == "__main__":
    main()
