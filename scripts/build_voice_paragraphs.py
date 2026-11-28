import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_voice_script import NON_UZ_SPELLING, WORD_RE, ok_sentence
from uzllm.clean import clean_uzbek

WIKI = ROOT / "data/raw/wikipedia/20231101.uz/train-00000-of-00001.parquet"
SAMPLE = ROOT / "data/sample/uz_sample.jsonl"
OUT = ROOT / "data/voice/paragraphs.jsonl"
N = 500
rng = random.Random(21)


def docs():
    for b in pq.ParquetFile(WIKI).iter_batches(batch_size=5000, columns=["text"]):
        for t in b.column("text").to_pylist():
            yield "wiki", clean_uzbek(t or "")
    with open(SAMPLE, encoding="utf-8") as f:
        for line in f:
            yield "web", json.loads(line)["text"]


def split_sents(par: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", par) if s.strip()]


def main():
    groups = []
    for src, text in docs():
        for par in text.split("\n"):
            sents = split_sents(par)
            run = []
            for s in sents + [""]:
                if s and ok_sentence(s, min_len=25, max_len=170):
                    run.append(s)
                    continue
                if len(run) >= 3:
                    groups.append((src, run[:6]))
                run = []
    print(f"Nomzod paragraflar: {len(groups):,}")

    tok = [[WORD_RE.findall(s.lower()) for s in g] for _, g in groups]
    wf = Counter(w for g in tok for ws in g for w in ws)
    bf = Counter(b for g in tok for ws in g for b in zip(ws, ws[1:]))
    good = []
    for (src, g), gt in zip(groups, tok):
        words = [w for ws in gt for w in ws]
        pairs = [p for ws in gt for p in zip(ws, ws[1:])]
        text = " ".join(g)
        if not (200 <= len(text) <= 650) or any(NON_UZ_SPELLING.search(w) for w in words):
            continue
        caps = sum(1 for s in g for w in s.split()[1:] if w[:1].isupper())
        common = sum(wf[w] >= 15 for w in words) / len(words)
        fluent = sum(bf[p] >= 2 for p in pairs) / max(1, len(pairs))
        if common >= 0.85 and fluent >= 0.45 and caps <= len(g) + 1:
            good.append({"sentences": g, "source": src, "score": common + fluent})
    rng.shuffle(good)
    wiki = [g for g in good if g["source"] == "wiki"][: N * 6 // 10]
    web = [g for g in good if g["source"] == "web"][: N - len(wiki)]
    chosen = wiki + web
    rng.shuffle(chosen)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for i, g in enumerate(chosen, 1):
            f.write(json.dumps({"id": f"p{i:04d}", "sentences": g["sentences"], "source": g["source"]},
                               ensure_ascii=False) + "\n")
    total_chars = sum(len(" ".join(g["sentences"])) for g in chosen)
    print(f"Tanlandi: {len(chosen)} paragraf ({len(wiki)} Vikipediya, {len(web)} boshqa), "
          f"~{total_chars / 14 / 60:.0f} daqiqa o'qish -> {OUT}")
    for g in chosen[:3]:
        print("\n  " + " ".join(g["sentences"]))


if __name__ == "__main__":
    main()
