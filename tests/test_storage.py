from uzllm.storage import SQLiteStore


def test_store_roundtrip(tmp_path):
    s = SQLiteStore(tmp_path / "a.db")
    cid = s.ensure_conversation(None, "Salom, bu birinchi xabar")
    assert s.ensure_conversation(cid, "x") == cid
    s.add_message(cid, "user", "Salom")
    bot = s.add_message(cid, "assistant", "Assalomu alaykum", {"tools": [], "sources": []})
    assert [m["role"] for m in s.history(cid)] == ["user", "assistant"]
    s.save_feedback(bot, -1, "Yaxshiroq javob")
    msgs = s.messages(cid)
    assert msgs[1]["rating"] == -1
    fb = s.export_feedback()
    assert fb[0]["question"] == "Salom" and fb[0]["correction"] == "Yaxshiroq javob"
    assert s.messages(cid, user_id="boshqa") == []
    assert s.list_conversations("boshqa") == []
    s.delete_conversation(cid)
    assert s.list_conversations() == []
