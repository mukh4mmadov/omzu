import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uzllm.clean import clean_uzbek
from uzllm.knowledge import KB_PATH, add_document, connect

WIKI = ROOT / "data/raw/wikipedia/20231101.uz/train-00000-of-00001.parquet"


def main():
    if KB_PATH.exists():
        KB_PATH.unlink()
    con = connect()
    t0 = time.time()
    n_docs = n_chunks = 0
    pf = pq.ParquetFile(WIKI)
    for batch in pf.iter_batches(batch_size=5000, columns=["title", "text"]):
        for title, text in zip(batch.column("title").to_pylist(), batch.column("text").to_pylist()):
            text = clean_uzbek(text or "")
            if len(text) < 150:
                continue
            n_chunks += add_document(con, clean_uzbek(title), text, source="wikipedia")
            n_docs += 1
        con.commit()
        print(f"  {n_docs:,} maqola, {n_chunks:,} bo'lak ({time.time() - t0:.0f}s)", flush=True)
    print("Indeks optimallashtirilmoqda...", flush=True)
    con.execute("INSERT INTO chunks(chunks) VALUES('optimize')")
    con.commit()
    con.close()
    print(f"Tayyor: {KB_PATH} ({KB_PATH.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
