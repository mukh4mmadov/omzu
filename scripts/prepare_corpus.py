import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uzllm.clean import clean_english, clean_uzbek

RAW = ROOT / "data" / "raw"

SOURCES = {
    "wiki": ("uz", RAW / "wikipedia/20231101.uz/train-00000-of-00001.parquet"),
    "fw2_latn": ("uz", RAW / "fineweb-2/data/uzn_Latn/train/000_00000.parquet"),
    "fw2_cyrl": ("uz", RAW / "fineweb-2/data/uzn_Cyrl/train/000_00000.parquet"),
    "edu0": ("en", RAW / "fineweb-edu/sample/10BT/000_00000.parquet"),
    "edu1": ("en", RAW / "fineweb-edu/sample/10BT/001_00000.parquet"),
}

MIN_CHARS = 200


def _clean_batch(args):
    lang, texts = args
    fn = clean_uzbek if lang == "uz" else clean_english
    return [t for t in (fn(x) for x in texts if x) if len(t) >= MIN_CHARS]


def iter_batches(path: Path, lang: str, batch_size: int = 2000):
    pf = pq.ParquetFile(path)
    for batch in pf.iter_batches(batch_size=batch_size, columns=["text"]):
        yield lang, batch.column("text").to_pylist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=list(SOURCES), help="qaysi manbalar")
    ap.add_argument("--out", default=str(ROOT / "data" / "clean"))
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_lang: dict[str, list[Path]] = {}
    for name in args.only:
        lang, path = SOURCES[name]
        by_lang.setdefault(lang, []).append(path)

    with Pool(processes=args.workers, maxtasksperchild=500) as pool:
        for lang, paths in by_lang.items():
            seen: set[bytes] = set()
            n_docs = n_chars = n_dup = 0
            out_path = out_dir / f"{lang}.jsonl"
            with open(out_path, "w", encoding="utf-8") as f:
                for path in paths:
                    if not path.exists():
                        print(f"  [topilmadi, o'tkazib yuborildi] {path}")
                        continue
                    print(f"  [{lang}] {path.relative_to(RAW)} ...", flush=True)
                    for docs in pool.imap(_clean_batch, iter_batches(path, lang), chunksize=1):
                        for d in docs:
                            h = hashlib.md5(d.encode("utf-8")).digest()
                            if h in seen:
                                n_dup += 1
                                continue
                            seen.add(h)
                            f.write(json.dumps({"text": d}, ensure_ascii=False) + "\n")
                            n_docs += 1
                            n_chars += len(d)
            print(f"[{lang}] {n_docs:,} hujjat, {n_chars / 1e9:.2f} mlrd belgi, "
                  f"{n_dup:,} takror olib tashlandi -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
