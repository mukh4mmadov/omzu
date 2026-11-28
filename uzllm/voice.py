import io
import json
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
VDIR = ROOT / "data" / "voice"
DEFAULT_SPEAKER = "ozodbek"
GOAL_SECONDS = 60 * 60
CONSENT_TEXT = ("Men ushbu ovoz yozuvlarimni OMZU sunʼiy intellekt modelini oʻqitish va OMZU mahsulotida "
                "ovoz sifatida ishlatish uchun ixtiyoriy ravishda beraman.")
_lock = threading.RLock()


def _spk_dir(speaker: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", speaker):
        raise ValueError("notoʻgʻri diktor nomi")
    return VDIR / "speakers" / speaker


def _rec(speaker: str) -> Path:
    return _spk_dir(speaker) / "recordings"


def _meta_path(speaker: str) -> Path:
    return _spk_dir(speaker) / "metadata.jsonl"


def _skip_path(speaker: str) -> Path:
    return _spk_dir(speaker) / "skipped.json"


def _migrate():
    old_meta = VDIR / "metadata.jsonl"
    if not old_meta.exists():
        return
    d = _spk_dir(DEFAULT_SPEAKER)
    d.mkdir(parents=True, exist_ok=True)
    if (VDIR / "recordings").exists() and not (d / "recordings").exists():
        shutil.move(str(VDIR / "recordings"), str(d / "recordings"))
    shutil.move(str(old_meta), str(d / "metadata.jsonl"))
    if (VDIR / "skipped.json").exists():
        shutil.move(str(VDIR / "skipped.json"), str(d / "skipped.json"))


def _speakers_path() -> Path:
    return VDIR / "speakers.json"


def _load_speakers() -> list[dict]:
    with _lock:
        _migrate()
        p = _speakers_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        owner = [{"id": DEFAULT_SPEAKER, "name": "Ozodbek Muhammadov", "role": "asosiy ovoz (loyiha egasi)",
                  "consent": {"text": CONSENT_TEXT, "date": datetime.now().isoformat(timespec="seconds")}}]
        VDIR.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(owner, ensure_ascii=False, indent=1), encoding="utf-8")
        return owner


def list_speakers() -> list[dict]:
    out = []
    for s in _load_speakers():
        meta = _meta(s["id"])
        out.append({"id": s["id"], "name": s["name"], "role": s.get("role", ""),
                    "consent_date": s["consent"]["date"][:10], "recorded": len(meta),
                    "seconds": round(sum(m["duration"] for m in meta.values()), 1)})
    return out


def add_speaker(name: str, consent: bool) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("ism kiritilmagan")
    if not consent:
        raise ValueError("rozilik berilmagan — boshqa odamning ovozini faqat uning roziligi bilan yozish mumkin")
    base = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("ʻ", "").replace("'", "")).strip("-")[:30] or "diktor"
    with _lock:
        spk = _load_speakers()
        sid, k = base, 2
        while any(s["id"] == sid for s in spk):
            sid, k = f"{base}-{k}", k + 1
        spk.append({"id": sid, "name": name, "role": "qoʻshimcha ovoz",
                    "consent": {"text": CONSENT_TEXT, "date": datetime.now().isoformat(timespec="seconds")}})
        _speakers_path().write_text(json.dumps(spk, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"id": sid, "name": name}


def _check_speaker(speaker: str):
    if not any(s["id"] == speaker for s in _load_speakers()):
        raise ValueError("bunday diktor yoʻq")


def _script() -> list[dict]:
    p = VDIR / "script.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def _paragraphs() -> list[dict]:
    p = VDIR / "paragraphs.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def _meta(speaker: str = DEFAULT_SPEAKER) -> dict[str, dict]:
    p = _meta_path(speaker)
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            m = json.loads(line)
            out[m["id"]] = m
    return out


def _write_meta(speaker: str, meta: dict[str, dict]):
    _meta_path(speaker).write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in meta.values()),
                                   encoding="utf-8")


def _skipped(speaker: str = DEFAULT_SPEAKER) -> set[str]:
    p = _skip_path(speaker)
    return set(json.loads(p.read_text())) if p.exists() else set()


def is_usable(m: dict) -> bool:
    return not m.get("warnings") and not m.get("rate_flag")


def _rate_check(speaker: str, text: str, duration: float) -> str | None:
    rates = [len(m["text"]) / max(m["duration"] - 0.4, 0.5) for m in _meta(speaker).values() if is_usable(m)]
    if len(rates) < 10:
        return None
    med = float(np.median(rates))
    r = len(text) / max(duration - 0.4, 0.5)
    if r > med * 1.4:
        return "juda tez oʻqildi — soʻz tushib qolmadimi? Qayta tinglab tekshiring"
    if r < med * 0.6:
        return "juda sekin yoki uzun pauza bor — adashib qayta oʻqilmadimi?"
    return None


def state(speaker: str = DEFAULT_SPEAKER, mode: str = "sentence") -> dict:
    _check_speaker(speaker)
    meta, skipped = _meta(speaker), _skipped(speaker)
    usable = {k: m for k, m in meta.items() if is_usable(m)}
    done_secs = sum(m["duration"] for m in usable.values())
    if mode == "paragraph":
        items = _paragraphs()
        done = {m["paragraph"] for m in usable.values() if m.get("paragraph")}
        tried = {m["paragraph"] for m in meta.values() if m.get("paragraph")}
    else:
        items = _script()
        done, tried = set(usable), set(meta)
    todo = [s for s in items if s["id"] not in done and s["id"] not in skipped]
    nxt = next((s for s in todo if s["id"] not in tried), None) or (todo[0] if todo else None)
    return {
        "speaker": speaker, "mode": mode, "total": len(items), "done_items": len(done & {i["id"] for i in items}),
        "recorded": len(usable), "rejected": len(meta) - len(usable), "skipped": len(skipped),
        "seconds": round(done_secs, 1), "goal_seconds": GOAL_SECONDS, "next": nxt,
        "with_warnings": len(meta) - len(usable),
    }


def analyze(audio: np.ndarray, sr: int) -> dict:
    x = audio.astype(np.float32)
    dur = len(x) / sr
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    frame = max(1, int(sr * 0.03))
    n = len(x) // frame
    if n < 5:
        return {"duration": dur, "peak": peak, "rms_db": -99.0, "snr_db": 0.0, "warnings": ["juda qisqa"]}
    e = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    rms_db = float(20 * np.log10(np.percentile(e, 90)))
    noise_db = float(20 * np.log10(np.percentile(e, 10)))
    snr = rms_db - noise_db
    warnings = []
    if dur < 1.5:
        warnings.append("juda qisqa — gapni toʻliq oʻqidingizmi?")
    if peak >= 0.99:
        warnings.append("ovoz juda baland (xirillash bor) — mikrofonni biroz uzoqlashtiring")
    if rms_db < -38:
        warnings.append("ovoz juda past — mikrofonga yaqinroq gapiring")
    if snr < 25:
        warnings.append("fon shovqini sezilarli — tinchroq joyda yozing")
    return {"duration": round(dur, 2), "peak": round(peak, 3), "rms_db": round(rms_db, 1),
            "snr_db": round(snr, 1), "warnings": warnings}


def _trim_bounds(x: np.ndarray, sr: int, pad: float = 0.25) -> tuple[int, int]:
    frame = max(1, int(sr * 0.02))
    n = len(x) // frame
    if n < 3:
        return 0, len(x)
    e = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1))
    thr = max(np.percentile(e, 10) * 3, 1e-3)
    idx = np.where(e > thr)[0]
    if not len(idx):
        return 0, len(x)
    return max(0, idx[0] * frame - int(pad * sr)), min(len(x), (idx[-1] + 1) * frame + int(pad * sr))


def _trim(x: np.ndarray, sr: int, pad: float = 0.25) -> np.ndarray:
    a, b = _trim_bounds(x, sr, pad)
    return x[a:b]


def clean_audio(x: np.ndarray, sr: int) -> np.ndarray:
    from scipy.signal import butter, sosfiltfilt
    x = x - float(np.mean(x))
    if len(x) > sr // 10:
        x = sosfiltfilt(butter(4, 60, "highpass", fs=sr, output="sos"), x).astype(np.float32)
    return x


def _read(data: bytes) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    return clean_audio(audio.mean(axis=1), sr), sr


def save_recording(sid: str, data: bytes, speaker: str = DEFAULT_SPEAKER) -> dict:
    _check_speaker(speaker)
    script = {s["id"]: s for s in _script()}
    if sid not in script:
        raise ValueError("bunday gap yoʻq")
    audio, sr = _read(data)
    audio = _trim(audio, sr)
    if len(audio) / sr > 30:
        raise ValueError("yozuv juda uzun (30 soniyadan ortiq) — bitta gap uchun. Qayta yozib koʻring.")
    rec_dir = _rec(speaker)
    rec_dir.mkdir(parents=True, exist_ok=True)
    sf.write(rec_dir / f"{sid}.wav", audio, sr, subtype="PCM_16")
    rec = {"id": sid, "text": script[sid]["text"], "file": f"recordings/{sid}.wav", "sr": sr,
           "created": datetime.now().isoformat(timespec="seconds"), **analyze(audio, sr)}
    flag = _rate_check(speaker, rec["text"], rec["duration"])
    if flag:
        rec["rate_flag"] = flag
        rec["warnings"] = [*rec["warnings"], flag]
    with _lock, open(_meta_path(speaker), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def split_by_pauses(x: np.ndarray, sr: int, sentences: list[str],
                    marks: list[float] | None = None) -> list[tuple[int, int]] | None:
    n = len(sentences)
    if n == 1:
        return [(0, len(x))]
    hop = int(sr * 0.02)
    m = len(x) // hop
    e = np.sqrt(np.mean(x[: m * hop].reshape(m, hop) ** 2, axis=1))
    e = np.convolve(e, np.ones(3) / 3, mode="same")
    thr = max(np.percentile(e, 15) * 2.5, 10 ** (-48 / 20))
    silent = e < thr
    runs, i = [], 0
    while i < m:
        if silent[i]:
            j = i
            while j < m and silent[j]:
                j += 1
            if j - i >= 9 and i > 10 and j < m - 10:
                runs.append(((i + j) / 2 * hop, (j - i) * hop / sr, i * hop / sr, j * hop / sr))
            i = j
        else:
            i += 1
    if len(runs) < n - 1:
        return None
    lens = np.array([len(s) for s in sentences], dtype=float)
    R, K = len(runs), n - 1
    use_marks = marks is not None and len(marks) == K
    if not use_marks:
        wts = np.array([len(s) + 6 * s.count(",") for s in sentences], dtype=float)
        expected = np.cumsum(wts)[:-1] / wts.sum() * len(x)
    INF = 1e18

    def c(k, r):
        center, dur, start, end = runs[r]
        if use_marks:
            mk = marks[k]
            if start > mk + 0.25 or end < mk - 1.5:
                return INF / 4
            return abs(min(max(mk, start), end) - mk) + 0.3 * abs(center / sr - mk) - 0.6 * dur
        return abs(center - expected[k]) / sr - 3.0 * dur

    cost = np.full((K, R), INF)
    back = np.zeros((K, R), dtype=int)
    for r in range(R):
        cost[0, r] = c(0, r)
    for k in range(1, K):
        best, arg = INF, -1
        for r in range(R):
            if r - 1 >= 0 and cost[k - 1, r - 1] < best:
                best, arg = cost[k - 1, r - 1], r - 1
            if arg >= 0:
                cost[k, r] = best + c(k, r)
                back[k, r] = arg
    r = int(np.argmin(cost[K - 1]))
    if cost[K - 1, r] >= INF / 8:
        return None
    picks = [r]
    for k in range(K - 1, 0, -1):
        r = back[k, r]
        picks.append(r)
    cuts = [int(runs[r][0]) for r in reversed(picks)]
    bounds = [0, *cuts, len(x)]
    segs = list(zip(bounds[:-1], bounds[1:]))
    rate = len(x) / lens.sum()
    for (a, b), L in zip(segs, lens):
        if not 0.45 <= (b - a) / (L * rate) <= 2.0:
            return None
    return segs


def _speaking_rate(speaker: str) -> float:
    rates = [len(m["text"]) / max(m["duration"] - 0.4, 0.5) for m in _meta(speaker).values() if is_usable(m)]
    return float(np.median(rates)) if len(rates) >= 5 else 15.0


def save_paragraph(pid: str, data: bytes, marks: list[float] | None = None,
                   speaker: str = DEFAULT_SPEAKER) -> dict:
    _check_speaker(speaker)
    paras = {p["id"]: p for p in _paragraphs()}
    if pid not in paras:
        raise ValueError("bunday matn yoʻq")
    sents = paras[pid]["sentences"]
    audio, sr = _read(data)
    if len(audio) / sr > 40 * len(sents):
        raise ValueError("yozuv gaplar soniga nisbatan juda uzun — qayta yozib koʻring.")
    a0, b0 = _trim_bounds(audio, sr)
    if marks:
        marks = [m - a0 / sr for m in marks]
    audio = audio[a0:b0]
    segs = split_by_pauses(audio, sr, sents, marks)
    if segs is not None:
        rate = _speaking_rate(speaker)
        for (a, b), s in zip(segs, sents):
            if not 0.6 * rate <= len(s) / max((b - a) / sr - 0.4, 0.3) <= 1.6 * rate:
                segs = None
                break
    if segs is None:
        unsplit = _spk_dir(speaker) / "unsplit"
        unsplit.mkdir(parents=True, exist_ok=True)
        sf.write(unsplit / f"{pid}.wav", audio, sr, subtype="PCM_16")
        return {"ok": False, "error": "Gaplar orasidagi pauzalarni aniq topa olmadim. Har gapni tugatgach "
                                      "Probelni bosing va qisqa (~0.5 soniya) toʻxtab, qayta oʻqib koʻring."}
    rec_dir = _rec(speaker)
    rec_dir.mkdir(parents=True, exist_ok=True)
    sf.write(rec_dir / f"{pid}.wav", audio, sr, subtype="PCM_16")
    out = []
    with _lock, open(_meta_path(speaker), "a", encoding="utf-8") as f:
        for k, ((a, b), text) in enumerate(zip(segs, sents), 1):
            seg = _trim(audio[a:b], sr, pad=0.15)
            sid = f"{pid}_{k}"
            sf.write(rec_dir / f"{sid}.wav", seg, sr, subtype="PCM_16")
            rec = {"id": sid, "paragraph": pid, "text": text, "file": f"recordings/{sid}.wav", "sr": sr,
                   "created": datetime.now().isoformat(timespec="seconds"), **analyze(seg, sr)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.append(rec)
    return {"ok": True, "id": pid, "segments": [{"id": r["id"], "duration": r["duration"]} for r in out],
            "duration": round(sum(r["duration"] for r in out), 2),
            "warnings": sorted({w for r in out for w in r["warnings"]}),
            "snr_db": round(float(np.mean([r["snr_db"] for r in out])), 1),
            "rms_db": round(float(np.mean([r["rms_db"] for r in out])), 1)}


def delete(item_id: str, speaker: str = DEFAULT_SPEAKER):
    with _lock:
        meta = _meta(speaker)
        if item_id.startswith("p"):
            meta = {k: v for k, v in meta.items() if v.get("paragraph") != item_id}
            files = list(_rec(speaker).glob(f"{item_id}*.wav"))
        else:
            meta.pop(item_id, None)
            files = [_rec(speaker) / f"{item_id}.wav"]
        _write_meta(speaker, meta)
        for p in files:
            p.unlink(missing_ok=True)


def skip(item_id: str, speaker: str = DEFAULT_SPEAKER):
    with _lock:
        s = _skipped(speaker)
        s.add(item_id)
        _spk_dir(speaker).mkdir(parents=True, exist_ok=True)
        _skip_path(speaker).write_text(json.dumps(sorted(s)))


def audio_path(item_id: str, speaker: str = DEFAULT_SPEAKER) -> Path | None:
    if not re.fullmatch(r"[sp]\d{4}(_\d{1,2})?", item_id):
        return None
    p = _rec(speaker) / f"{item_id}.wav"
    return p if p.exists() else None
