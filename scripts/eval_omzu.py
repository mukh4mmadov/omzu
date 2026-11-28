import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

Q = [
    ("fact", "Amir Temur kim?", "sarkarda|temuriylar|1336|hukmdor|amir"),
    ("fact", "Alisher Navoiy kim bo'lgan?", "shoir|mutafakkir|1441|xamsa|adabiyot"),
    ("fact", "Toshkent qaysi davlatning poytaxti?", "oʻzbekiston|uzbekistan"),
    ("fact", "Samarqand qaysi viloyatda joylashgan?", "samarqand viloyat|viloyat"),
    ("fact", "Mirzo Ulug'bek kim edi?", "astronom|temuriy|rasadxona|olim|matematik"),
    ("fact", "Ibn Sino kim?", "tabib|vrach|tibbiyot|faylasuf|olim|qonun"),
    ("fact", "Al-Xorazmiy nima bilan mashhur?", "algebra|matematik|algoritm"),
    ("fact", "Orol dengizi nima uchun qurib qoldi?", "sugʻor|daryo|amudaryo|sirdaryo|paxta"),
    ("fact", "Oʻzbekiston mustaqilligi qachon e'lon qilingan?", "1991"),
    ("fact", "Buxoro qanday shahar?", "qadimiy|tarixiy|shahar|meʼmoriy"),
    ("fact", "Xiva qayerda joylashgan?", "xorazm|ichan"),
    ("fact", "Fargʻona vodiysi qaysi viloyatlarni oʻz ichiga oladi?", "andijon|namangan|fargʻona"),
    ("fact", "Navroʻz bayrami nima?", "bahor|yangi yil|21 mart|bayram"),
    ("fact", "Python nima?", "dasturlash"),
    ("fact", "Ipak yoʻli nima?", "savdo|yoʻl|karvon"),
    ("fact", "Bobur kim?", "shoh|bobur|moʻgʻul|hind|shoir|temuriy"),
    ("fact", "Amudaryo qayerdan oqadi?", "pomir|afgʻon|tojik|orol|daryo"),
    ("fact", "Oʻzbekistonda necha viloyat bor?", "12|13|viloyat"),
    ("why", "Nima uchun osmon koʻk?", "sochil|yorugʻlik|toʻlqin|rayleigh|atmosfera"),
    ("why", "Nima uchun yomgʻir yogʻadi?", "bugʻ|bulut|kondensats|suv"),
    ("why", "Fotosintez nima va u qanday ishlaydi?", "quyosh|yorugʻlik|xlorofill|kislorod|uglerod"),
    ("why", "Nima uchun qish sovuq boʻladi?", "quyosh|yer|egilish|burchak|nur|oʻq"),
    ("why", "Suv qanday qilib muzga aylanadi?", "0|sovu|muz|harorat|kristal"),
    ("why", "Nima uchun odamlar uxlaydi?", "dam|miya|tana|energiya|tiklan"),
    ("why", "Yurak qanday ishlaydi?", "qon|nasos|torak|qisqar"),
    ("why", "Nima uchun Oy shaklini oʻzgartiradi?", "quyosh|yoritil|fazalar|aylan|yer"),
    ("why", "Vitamin C nima uchun kerak?", "immunitet|shamollash|organizm|antioksidant|tana"),
    ("why", "Zilzila nima uchun sodir boʻladi?", "plita|yer qobigʻ|tektonik|siljish|yer"),
    ("persona", "Sen kimsan?", "omzu"),
    ("persona", "Seni kim yaratgan?", "ozodbek"),
    ("persona", "Isming nima?", "omzu"),
    ("persona", "Siz qaysi tillarda gaplasha olasiz?", "oʻzbek|uzbek|ingliz"),
    ("persona", "Nimalar qila olasan?", "ob-havo|eslatma|valyuta"),
    ("tool", "25 * 4 + 10 nechaga teng?", "110"),
    ("tool", "100 / 8 hisobla", "12.5|12,5"),
    ("tool", "2 ning 10-darajasi nechaga teng? 2**10", "1024"),
    ("tool", "Dollar kursi qancha?", "soʻm|so'm"),
    ("tool", "Samarqandda ob-havo qanday?", "°|daraja|harorat"),
    ("tool", "Bugun qaysi kun?", "202"),
    ("idk", "Mening bobomning ismi nima?", "IDK"),
    ("idk", "Kecha Toshkentdagi futbol oʻyini natijasi qanday boʻldi?", "IDK"),
    ("idk", "Qoʻshnimning telefon raqami nima?", "IDK"),
    ("idk", "Zorgʻanlar qishlogʻining aholisi necha kishi?", "IDK"),
    ("idk", "Xyzqwerty degan shahar qaerda?", "IDK"),
    ("en", "What is the capital of Uzbekistan?", "tashkent"),
    ("en", "Who wrote the Divine Comedy?", "dante"),
    ("en", "What is 12 times 12?", "144"),
    ("en", "What is photosynthesis?", "light|sun|plant|energy|glucose"),
    ("en", "What is the boiling point of water in Celsius?", "100"),
    ("en", "Who are you?", "omzu"),
    ("en", "What is Python used for?", "programming|code|data|web"),
    ("en", "Why is the sky blue?", "scatter|light|wavelength|atmosphere|rayleigh"),
]

IDK_RE = re.compile(r"(aniq maʼlumotim yoʻq|aniq ma'lumotim yo'q|bilmayman|topa olmadim|ishonchli ma.lumot|"
                    r"menda .{0,30}ma.lumot yo|don.t (have|know)|not sure|no reliable)", re.I)


def norm(t: str) -> str:
    return t.lower().replace("ʻ", "ʻ").replace("’", "ʼ").replace("'", "ʼ").replace("ʻ", "ʻ").replace("ʼ", "ʻ")


def grade(kind: str, expect: str, ans: str) -> bool:
    if kind == "idk":
        return bool(IDK_RE.search(ans))
    a = norm(ans)
    return any(norm(k) in a for k in expect.split("|"))


def main():
    from uzllm import assistant
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--save", default="")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    for kv in filter(None, args.cfg.split(",")):
        k, _, v = kv.partition("=")
        if k == "loose":
            assistant.STRICT_CONTEXT = False
        elif k in ("temp", "temperature"):
            assistant.GEN["temperature"] = float(v)
        elif k == "rep":
            assistant.GEN["repetition_penalty"] = float(v)
        elif k == "topk":
            assistant.GEN["top_k"] = int(v)
        elif k == "topp":
            assistant.GEN["top_p"] = float(v)
    only = set(filter(None, args.only.split(",")))
    items = [q for q in Q if not only or q[0] in only]
    assistant.get_chat_model()
    res = defaultdict(list)
    log = []
    t0 = time.time()
    for kind, q, expect in items:
        ans = "".join(e["text"] for e in assistant.respond([{"role": "user", "content": q}]) if e["type"] == "token")
        ok = grade(kind, expect, ans)
        res[kind].append(ok)
        log.append({"kind": kind, "q": q, "ok": ok, "a": ans})
        if args.show or not ok:
            print(("OK " if ok else "XX ") + f"[{kind}] {q}\n     {ans[:260].replace(chr(10), ' ')}")
    print("\n=== NATIJA", args.cfg or "(standart)", f"({time.time() - t0:.0f}s) ===")
    tot = sum(map(sum, res.values()))
    for k, v in res.items():
        print(f"  {k:8s} {sum(v):2d}/{len(v):2d}  {100 * sum(v) / len(v):3.0f}%")
    print(f"  JAMI     {tot}/{len(items)}  {100 * tot / len(items):.0f}%")
    if args.save:
        Path(args.save).write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
