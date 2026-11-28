import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uzllm.tokenizer import train_tokenizer


def sample_texts(path: Path, max_chars: float):
    if max_chars <= 0 or not path.exists():
        return
    total = path.stat().st_size
    keep_every = max(1, int(total / max_chars))
    got = 0
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i % keep_every:
                continue
            t = json.loads(line)["text"]
            got += len(t)
            yield t
            if got >= max_chars:
                break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "clean"))
    ap.add_argument("--uz-chars", type=float, default=250e6)
    ap.add_argument("--en-chars", type=float, default=120e6)
    ap.add_argument("--vocab", type=int, default=32000)
    ap.add_argument("--out", default=str(ROOT / "data" / "tokenizer.json"))
    args = ap.parse_args()

    data = Path(args.data)

    def texts():
        yield from sample_texts(data / "uz.jsonl", args.uz_chars)
        yield from sample_texts(data / "en.jsonl", args.en_chars)

    tok = train_tokenizer(texts(), vocab_size=args.vocab)
    tok.save(args.out)
    print(f"Tokenizer saqlandi: {args.out} (lug'at: {tok.get_vocab_size()})")

    for s in ["Oʻzbekiston Respublikasi poytaxti Toshkent shahri hisoblanadi.",
              "Ertaga soat 9 da uchrashuvni eslatib qoʻying.",
              "The quick brown fox jumps over the lazy dog."]:
        ids = tok.encode(s).ids
        print(f"{len(ids):3d} token | {s}")
        print("     ", [tok.decode([i]) for i in ids])


if __name__ == "__main__":
    main()
