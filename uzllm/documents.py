import io
import re
from html.parser import HTMLParser

from uzllm import knowledge
from uzllm.clean import clean_english, clean_uzbek, cyrillic_ratio

SUPPORTED = {".pdf", ".docx", ".md", ".markdown", ".txt", ".html", ".htm", ".csv", ".json",
             ".js", ".ts", ".py", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".php", ".rb", ".css", ".sql"}
MAX_BYTES = 30 * 1024 * 1024


class _HTMLText(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "pre", "section", "article", "dt", "dd"}

    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def extract_text(filename: str, data: bytes) -> str:
    ext = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in SUPPORTED:
        raise ValueError(f"{ext or 'bu'} turidagi fayl qo'llab-quvvatlanmaydi")
    if len(data) > MAX_BYTES:
        raise ValueError("fayl juda katta (30 MB dan oshmasin)")
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join((p.extract_text() or "") for p in reader.pages)
    elif ext == ".docx":
        import docx
        d = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in d.paragraphs)
    elif ext in (".html", ".htm"):
        p = _HTMLText()
        p.feed(data.decode("utf-8", errors="replace"))
        text = "".join(p.out)
    else:
        text = data.decode("utf-8", errors="replace")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()
    if not text:
        raise ValueError("fayldan matn topilmadi (skaner qilingan rasm bo'lishi mumkin)")
    return text


def add_file(filename: str, data: bytes) -> dict:
    text = extract_text(filename, data)
    uz_like = cyrillic_ratio(text) > 0.3 or re.search(r"\b(va|bilan|uchun|ham|bu)\b", text[:5000]) is not None
    text = clean_uzbek(text) if uz_like else clean_english(text)
    con = knowledge.connect()
    try:
        con.execute("DELETE FROM chunks WHERE source=?", (f"user:{filename}",))
        n = knowledge.add_document(con, filename.rsplit(".", 1)[0], text, source=f"user:{filename}")
        con.commit()
    finally:
        con.close()
    return {"name": filename, "chunks": n, "chars": len(text)}


def list_files() -> list[dict]:
    con = knowledge.connect()
    try:
        rows = con.execute("SELECT source, count(*), sum(length(text)) FROM chunks "
                           "WHERE source LIKE 'user:%' GROUP BY source ORDER BY source").fetchall()
    finally:
        con.close()
    return [{"name": s[5:], "chunks": n, "chars": c} for s, n, c in rows]


def delete_file(name: str) -> bool:
    con = knowledge.connect()
    try:
        n = con.execute("DELETE FROM chunks WHERE source=?", (f"user:{name}",)).rowcount
        con.commit()
    finally:
        con.close()
    return n > 0
