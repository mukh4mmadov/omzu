import re
import sqlite3
from pathlib import Path

KB_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge.db"

CHUNK_CHARS = 700

STOPWORDS = {
    "va", "bilan", "uchun", "bu", "u", "bir", "ham", "esa", "deb", "edi", "qanday", "nima", "nimа",
    "qachon", "qayerda", "kim", "necha", "qancha", "haqida", "menga", "ayt", "aytib", "ber", "bering",
    "the", "a", "an", "of", "is", "what", "who", "when", "where", "how", "in", "to", "and",
    "qiladi", "qilish", "qilinadi", "ishlaydi", "ishlatiladi", "beradi", "boʻladi", "degani", "nimadir",
    "tushuntir", "tushuntirib", "does", "do", "use", "used", "work", "works", "mean",
    "maʼlumot", "malumot", "maʼlumotlar", "shahri", "shahar", "shahrining", "bering", "beringchi",
}


def connect(path: Path = KB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
        title, text, source UNINDEXED, pos UNINDEXED, tokenize='unicode61 remove_diacritics 0')""")
    return con


def split_chunks(text: str, max_chars: int = CHUNK_CHARS) -> list[str]:
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(p) > max_chars:
            sents = re.split(r"(?<=[.!?])\s+", p)
        else:
            sents = [p]
        for s in sents:
            if cur and len(cur) + len(s) + 1 > max_chars:
                chunks.append(cur)
                cur = s
            else:
                cur = f"{cur}\n{s}" if cur else s
    if cur:
        chunks.append(cur)
    return chunks


def add_document(con, title: str, text: str, source: str = "user"):
    rows = [(title, c, source, i) for i, c in enumerate(split_chunks(text))]
    con.executemany("INSERT INTO chunks(title, text, source, pos) VALUES (?,?,?,?)", rows)
    return len(rows)


def _title_overlap(terms: list[str], title: str) -> float:
    words = re.findall(r"[\wʻʼ]+", title.lower())
    if not terms or not words:
        return 0.0
    hit = sum(any(w.startswith(t) for w in words) for t in terms)
    extra = sum(not any(w.startswith(t) for t in terms) for w in words)
    return hit / len(terms) - 0.25 * extra


def _query_terms(query: str) -> list[str]:
    words = re.findall(r"[\wʻʼ]+", query.lower())
    terms = []
    for w in words:
        if w in STOPWORDS or len(w) < 2:
            continue
        stem = w if len(w) <= 4 else w[: max(4, len(w) - 3)]
        terms.append(stem.replace('"', ""))
    return terms


def search(query: str, k: int = 3, con: sqlite3.Connection | None = None) -> list[dict]:
    own = con is None
    con = con or connect()
    terms = _query_terms(query)
    if not terms:
        return []
    qlow = query.lower()
    results = []
    for joiner in (" AND ", " OR "):
        fts = joiner.join(f'"{t}"*' for t in terms)
        try:
            rows = con.execute(
                "SELECT title, text, source, pos, bm25(chunks, 5.0, 1.0) AS score FROM chunks "
                "WHERE chunks MATCH ? ORDER BY score LIMIT 60", (fts,)).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if rows:
            scored = []
            for title, text, source, pos, bm in rows:
                rel = -bm
                ov = _title_overlap(terms, title)
                rel *= 1 + 2.0 * max(0.0, ov)
                if ov >= 0.999:
                    rel *= 2.0
                base_title = re.sub(r"\s*\(.*\)$", "", title.lower())
                if len(base_title) > 2 and re.search(r"\b" + re.escape(base_title) + r"\b", qlow):
                    rel *= 2.5
                if pos == 0 and source == "wikipedia":
                    rel *= 1.3
                if source.startswith("user:"):
                    rel *= 1.8
                scored.append((rel, {"title": title, "text": text, "source": source, "score": round(rel, 3)}))
            scored.sort(key=lambda x: -x[0])
            results = [s[1] for s in scored[:k]]
            break
    if own:
        con.close()
    return results
