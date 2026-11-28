from datetime import datetime

import pytest

from uzllm import tools


def test_calculator():
    assert tools.calculator("2+2*3")["result"] == 8
    assert tools.calculator("15% of 200")["result"] == 30
    assert tools.calculator("200 * 15%")["result"] == 30
    assert tools.calculator("sqrt(144)")["result"] == 12
    assert tools.calculator("3,5 * 2")["result"] == 7
    assert "error" in tools.calculator("1/0")
    assert "error" in tools.calculator("__import__('os')")


def test_parse_when():
    now = datetime(2026, 11, 19, 15, 0)
    assert tools._parse_when("30 daqiqa", now) == datetime(2026, 11, 19, 15, 30)
    assert tools._parse_when("2 soat", now) == datetime(2026, 11, 19, 17, 0)
    assert tools._parse_when("ertaga 09:00", now) == datetime(2026, 11, 20, 9, 0)
    assert tools._parse_when("18:30", now) == datetime(2026, 11, 19, 18, 30)
    assert tools._parse_when("10:00", now) == datetime(2026, 11, 20, 10, 0)
    assert tools._parse_when("qachondir", now) is None


def test_reminders_and_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "DB_PATH", tmp_path / "t.db")
    r = tools.add_reminder("Uchrashuv", "ertaga 09:00")
    assert r["id"] == 1
    assert len(tools.list_reminders()["reminders"]) == 1
    tools.call_tool("remember", {"fact": "Foydalanuvchi dasturchi"})
    assert tools.list_memories()["memories"][0]["fact"] == "Foydalanuvchi dasturchi"
    assert tools.forget(1)["deleted"]
    assert tools.call_tool("nonexistent")["error"]


@pytest.mark.network
def test_live_weather_and_currency():
    w = tools.weather("Samarkand")
    assert "now" in w, w
    c = tools.currency("USD", 100)
    assert c["rate_uzs"] > 1000, c


def test_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "DB_PATH", tmp_path / "t.db")
    a = tools.add_task("bozorga borish", "ertaga")
    tools.add_task("kitob oʻqish")
    assert a["due"] is not None
    assert [t["text"] for t in tools.list_tasks()["tasks"]] == ["bozorga borish", "kitob oʻqish"]
    assert tools.complete_task(text="bozorga bordim")["text"] == "bozorga borish"
    assert len(tools.list_tasks()["tasks"]) == 1
    assert len(tools.list_tasks(include_done=True)["tasks"]) == 2
    assert "error" in tools.complete_task(id=99)
