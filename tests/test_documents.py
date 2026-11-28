import pytest

from uzllm import documents, knowledge


def test_extract_html_and_text():
    html = b"<html><head><style>x{}</style></head><body><h1>Array.map()</h1><p>map() yangi massiv qaytaradi.</p><script>bad()</script></body></html>"
    t = documents.extract_text("map.html", html)
    assert "Array.map()" in t and "yangi massiv" in t and "bad()" not in t
    assert documents.extract_text("a.md", "# Salom\n\nMatn".encode()) == "# Salom\n\nMatn"
    with pytest.raises(ValueError):
        documents.extract_text("rasm.png", b"\x89PNG")


def test_add_search_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge, "KB_PATH", tmp_path / "kb.db")
    monkeypatch.setattr(knowledge.connect, "__defaults__", (tmp_path / "kb.db",))
    doc = ("JavaScript massivlari\n\nArray.prototype.map() metodi massivning har bir elementiga funksiyani qo'llaydi "
           "va natijalardan yangi massiv qaytaradi. Misol: [1, 2, 3].map(x => x * 2) natijasi [2, 4, 6].")
    info = documents.add_file("js-massivlar.md", doc.encode())
    assert info["chunks"] >= 1
    assert documents.list_files()[0]["name"] == "js-massivlar.md"
    hits = knowledge.search("map metodi nima qiladi?")
    assert hits and hits[0]["source"] == "user:js-massivlar.md"
    assert documents.delete_file("js-massivlar.md")
    assert documents.list_files() == []
