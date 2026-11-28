import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uzllm.clean import clean_uzbek, cyrillic_ratio

CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
FOREIGN = re.compile(r"[şçğıöüŞÇĞİÖÜəƏäÄñÑßәғқңөұүһіӘҒҚҢӨҰҮҺІ]")
META = re.compile(r"(parchada|matnda (aytil|keltiril|koʻrsatil)|ushbu matn|passage|berilgan matn)", re.I)


def _json(text: str):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"(\[.*\]|\{.*\})", t, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                return None
    return None


def check_pair(q: str, a: str, kind: str) -> str | None:
    if not isinstance(q, str) or not isinstance(a, str):
        return "turi"
    if len(q) < 8 or len(a) < 25:
        return "qisqa"
    both = q + " " + a
    if CJK.search(both):
        return "xitoycha"
    if cyrillic_ratio(both) > 0.01:
        return "kirill"
    if FOREIGN.search(both):
        return "turkcha/qozoqcha"
    if kind == "wiki" and META.search(both):
        return "matnga ishora"
    words = re.findall(r"[a-zA-Zʻʼ']+", a.lower())
    if words and Counter(words).most_common(1)[0][1] > max(12, len(words) * 0.15):
        return "takror"
    return None


def load(paths: list[str], stats: Counter | None = None) -> list[dict]:
    stats = stats if stats is not None else Counter()
    out, seen = [], set()
    for p in paths:
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            if r.get("finish") == "length":
                stats["chala"] += 1
                continue
            j = _json(r["text"])
            pairs = j if isinstance(j, list) else [j] if isinstance(j, dict) else None
            if not pairs:
                stats["json"] += 1
                continue
            for pr in pairs:
                if not isinstance(pr, dict):
                    stats["json"] += 1
                    continue
                q, a = pr.get("q"), pr.get("a")
                why = check_pair(q, a, r["kind"])
                if why:
                    stats[why] += 1
                    continue
                q, a = clean_uzbek(q.strip()), clean_uzbek(a.strip())
                key = re.sub(r"\W+", "", q.lower())
                if key in seen:
                    stats["takroriy savol"] += 1
                    continue
                seen.add(key)
                stats["ok:" + r["kind"]] += 1
                out.append({"q": q, "a": a, "kind": r["kind"], "model": r.get("model", "")})
    return out


def main():
    paths = sys.argv[1:] or sorted(glob.glob(str(ROOT / "data" / "teacher" / "out*.jsonl")))
    st = Counter()
    pairs = load(paths, st)
    print(f"{len(pairs)} ta yaroqli juftlik  |  {dict(st)}")
    for k in ("wiki", "topic", "oasst"):
        for p in [x for x in pairs if x["kind"] == k][:2]:
            print(f"\n[{k} | {p['model']}]\nS: {p['q']}\nJ: {p['a'][:600]}")


if __name__ == "__main__":
    main()
