import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uztts.text import normalize, tokenize

SRC = ROOT / "data" / "clean" / "uz.jsonl"
if not SRC.exists():
    SRC = ROOT / "data" / "sample" / "uz_sample.jsonl"
OUT = ROOT / "data" / "voice" / "script.jsonl"
N_SENTENCES = 1500
rng = random.Random(7)

OK_CHARS = re.compile(r"^[A-Za-zʻʼ ,.!?;:\-—«»\"']+$")
BAD = re.compile(r"\b(www|http|com|uz|ru|jpg|png)\b|[A-Z]{3,}|\s-\s*$|^\W")
COMMON_FOREIGN = re.compile(r"(?i)\b(the|and|of|is|ova|ovich|sky|shvili)\b")


def ok_sentence(s: str, min_len: int = 35, max_len: int = 150) -> bool:
    if not (min_len <= len(s) <= max_len) or not s.endswith((".", "!", "?")):
        return False
    if not OK_CHARS.match(s) or BAD.search(s) or COMMON_FOREIGN.search(s):
        return False
    if not s[0].isupper() or s.count(",") > 3 or s.count("«") != s.count("»"):
        return False
    words = s.split()
    return len(words) >= 5 and max(len(w) for w in words) <= 18


def candidates(limit_docs: int = 400_000):
    seen = set()
    with open(SRC, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit_docs:
                break
            if i % 3:
                continue
            text = json.loads(line)["text"]
            for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")):
                s = s.strip()
                if not ok_sentence(s):
                    continue
                key = s.lower()
                if key in seen:
                    continue
                seen.add(key)
                yield s


def units(s: str) -> set:
    toks = [t for t in tokenize(normalize(s)) if t not in " ,.!?-:;…"]
    return set(toks) | {a + b for a, b in zip(toks, toks[1:])}


WORD_RE = re.compile(r"[a-zʻʼ']+")


NON_UZ_SPELLING = re.compile(r"w|c(?!h)|th|ph|ck|ee|oo|qu|ts?ya")


def natural_uzbek(pool: list[str]) -> list[str]:
    tokenized = [WORD_RE.findall(s.lower()) for s in pool]
    wf = Counter(w for ws in tokenized for w in ws)
    bf = Counter(b for ws in tokenized for b in zip(ws, ws[1:]))
    out = []
    for s, words in zip(pool, tokenized):
        if len(words) < 5 or any(NON_UZ_SPELLING.search(w) for w in words):
            continue
        common = sum(wf[w] >= 25 for w in words) / len(words)
        caps = sum(1 for w in s.split()[1:] if w[:1].isupper())
        pairs = list(zip(words, words[1:]))
        fluent = sum(bf[p] >= 3 for p in pairs) / len(pairs)
        if min(wf[w] for w in words) >= 4 and common >= 0.85 and caps <= 1 and fluent >= 0.6:
            out.append(s)
    return out


def main():
    pool = list(candidates(limit_docs=900_000))
    print(f"Barcha nomzodlar: {len(pool):,}")
    pool = natural_uzbek(pool)
    rng.shuffle(pool)
    pool = pool[:60_000]
    print(f"Tabiiy o'zbekcha gaplar: {len(pool):,}")
    feats = [units(s) for s in pool]
    freq = Counter(u for f in feats for u in f)
    common_units = {u for u, c in freq.items() if c >= 20}
    feats = [f & common_units for f in feats]
    covered: Counter = Counter()
    chosen, used = [], set()
    for _ in range(N_SENTENCES):
        best, best_score = None, -1.0
        for i in rng.sample(range(len(pool)), 3000):
            if i in used:
                continue
            score = sum(1.0 / (1 + covered[u]) for u in feats[i]) / (len(pool[i]) ** 0.5)
            if score > best_score:
                best, best_score = i, score
        used.add(best)
        chosen.append(pool[best])
        covered.update(feats[best])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for k, s in enumerate(chosen, 1):
            f.write(json.dumps({"id": f"s{k:04d}", "text": s}, ensure_ascii=False) + "\n")
    all_units = {u for u, c in freq.items() if c >= 20}
    print(f"Tanlandi: {len(chosen)} gap -> {OUT}")
    print(f"Qamrov: {len(set(covered) & all_units)}/{len(all_units)} tez-tez uchraydigan tovush birikmasi")
    for s in chosen[:8]:
        print("  •", s)


if __name__ == "__main__":
    main()
