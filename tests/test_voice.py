import io
import json

import numpy as np
import pytest
import soundfile as sf

from uzllm import voice


def _wav(seconds=3.0, sr=48000, amp=0.3, noise=0.0005, silence=0.5):
    t = np.arange(int(seconds * sr)) / sr
    speech = amp * np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    pad = np.zeros(int(silence * sr))
    x = np.concatenate([pad, speech, pad]) + noise * np.random.default_rng(0).standard_normal(len(pad) * 2 + len(t))
    buf = io.BytesIO()
    sf.write(buf, x.astype(np.float32), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


@pytest.fixture
def vdir(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "VDIR", tmp_path)
    (tmp_path / "script.jsonl").write_text(
        "\n".join(json.dumps({"id": f"s000{i}", "text": f"Gap {i}."}) for i in range(1, 4)), encoding="utf-8")
    return tmp_path


def test_record_flow(vdir):
    st = voice.state()
    assert st["total"] == 3 and st["next"]["id"] == "s0001"
    rec = voice.save_recording("s0001", _wav())
    assert 3.0 <= rec["duration"] <= 3.6
    assert rec["warnings"] == []
    voice.skip("s0002")
    assert voice.state()["next"]["id"] == "s0003"
    loud = voice.save_recording("s0003", _wav(amp=1.2, noise=0.05))
    assert any("baland" in w for w in loud["warnings"]) and any("shovqin" in w for w in loud["warnings"])
    voice.delete("s0003")
    assert voice.state()["recorded"] == 1


def test_speakers_are_separate_and_need_consent(vdir):
    assert [s["id"] for s in voice.list_speakers()] == ["ozodbek"]
    with pytest.raises(ValueError):
        voice.add_speaker("Dilnoza", consent=False)
    sp = voice.add_speaker("Dilnoza Karimova", consent=True)
    assert sp["id"] == "dilnoza-karimova"
    voice.save_recording("s0001", _wav(), speaker=sp["id"])
    assert voice.state("ozodbek")["recorded"] == 0
    assert voice.state(sp["id"])["recorded"] == 1
    with pytest.raises(ValueError):
        voice.state("../hack")


def test_migrates_old_layout(vdir):
    (vdir / "recordings").mkdir()
    sf.write(vdir / "recordings" / "s0001.wav", np.zeros(4800, np.float32), 48000)
    (vdir / "metadata.jsonl").write_text(json.dumps({"id": "s0001", "text": "Gap 1.", "file": "recordings/s0001.wav",
                                                     "duration": 0.1, "created": "x"}) + "\n", encoding="utf-8")
    assert voice.list_speakers()[0]["recorded"] == 1
    assert voice.audio_path("s0001") is not None


def test_paragraph_split(vdir):
    sents = ["Birinchi gap bu yerda turibdi.", "Ikkinchi gap esa biroz uzunroq boʻlib chiqdi.", "Uchinchi gap."]
    (vdir / "paragraphs.jsonl").write_text(json.dumps({"id": "p0001", "sentences": sents}), encoding="utf-8")
    sr = 16000
    rng = np.random.default_rng(1)
    parts, marks, t = [], [], 0.0
    for k, s in enumerate(sents):
        d = len(s) / 15
        tt = np.arange(int(d * sr)) / sr
        parts.append((0.3 * np.sin(2 * np.pi * 200 * tt) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * tt))).astype(np.float32))
        t += d
        if k < len(sents) - 1:
            parts.append((0.001 * rng.standard_normal(int(0.6 * sr))).astype(np.float32))
            marks.append(t + 0.3)
            t += 0.6
    x = np.concatenate([np.zeros(sr // 2, np.float32), *parts, np.zeros(sr // 2, np.float32)])
    marks = [m + 0.5 for m in marks]
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV")
    res = voice.save_paragraph("p0001", buf.getvalue(), marks)
    assert res["ok"], res
    assert [s["id"] for s in res["segments"]] == ["p0001_1", "p0001_2", "p0001_3"]
    assert voice.state(mode="paragraph")["done_items"] == 1
    voice.delete("p0001")
    assert voice.state(mode="paragraph")["done_items"] == 0
