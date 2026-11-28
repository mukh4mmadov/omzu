import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uzllm.tokenizer import EOT, load_tokenizer

VAL_EVERY = 200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "clean"))
    ap.add_argument("--tokenizer", default=str(ROOT / "data" / "tokenizer.json"))
    ap.add_argument("--out", default=str(ROOT / "data" / "tokens"))
    ap.add_argument("--batch", type=int, default=4000)
    args = ap.parse_args()

    tok = load_tokenizer(args.tokenizer)
    eot = tok.token_to_id(EOT)
    assert tok.get_vocab_size() < 2**16
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"vocab_size": tok.get_vocab_size(), "eot_id": eot, "files": {}}

    for lang in ["uz", "en"]:
        src = Path(args.data) / f"{lang}.jsonl"
        if not src.exists():
            continue
        files = {s: open(out / f"{lang}_{s}.bin", "wb") for s in ("train", "val")}
        counts = {"train": 0, "val": 0}
        chars = 0
        doc_i = 0

        def flush(batch):
            nonlocal doc_i
            for enc in tok.encode_batch(batch):
                split = "val" if doc_i % VAL_EVERY == 0 else "train"
                arr = np.array(enc.ids + [eot], dtype=np.uint16)
                arr.tofile(files[split])
                counts[split] += len(arr)
                doc_i += 1

        with open(src, encoding="utf-8") as f:
            batch = []
            for line in f:
                t = json.loads(line)["text"]
                chars += len(t)
                batch.append(t)
                if len(batch) >= args.batch:
                    flush(batch)
                    batch = []
                    if doc_i % (args.batch * 25) == 0:
                        print(f"  [{lang}] {doc_i:,} hujjat, {counts['train'] / 1e6:,.0f}M token", flush=True)
            if batch:
                flush(batch)
        for fh in files.values():
            fh.close()
        meta["files"][lang] = counts
        print(f"[{lang}] train: {counts['train'] / 1e6:,.1f}M token, val: {counts['val'] / 1e6:,.2f}M token, "
              f"o'rtacha {chars / max(1, counts['train'] + counts['val']):.2f} belgi/token", flush=True)

    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print("Tayyor:", out)


if __name__ == "__main__":
    main()
