import hashlib
import json
import secrets
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from uzllm import voice

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
RECORD_SITE = "https://omzu-ovoz.vercel.app"


def _env() -> dict:
    out = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def configured() -> bool:
    e = _env()
    return bool(e.get("SUPABASE_URL") and e.get("SUPABASE_SECRET_KEY"))


def _req(method: str, path: str, body=None, raw: bytes | None = None, headers: dict | None = None,
         expect_json: bool = True):
    e = _env()
    key = e["SUPABASE_SECRET_KEY"]
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
         "User-Agent": "omzu/0.1", **(headers or {})}
    req = urllib.request.Request(e["SUPABASE_URL"] + path, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=120) as r:
        out = r.read()
    return json.loads(out) if expect_json and out else out


def create_invite(note: str = "") -> dict:
    token = secrets.token_urlsafe(32)
    speaker_id = "remote-" + secrets.token_hex(3)
    row = _req("POST", "/rest/v1/voice_invites", {
        "token_hash": hashlib.sha256(token.encode()).hexdigest(), "speaker_id": speaker_id,
        "speaker_name": note or None}, headers={"Prefer": "return=representation"})[0]
    site = _env().get("RECORD_SITE") or RECORD_SITE
    return {"id": row["id"], "speaker_id": speaker_id, "link": f"{site}/#t={token}"}


def list_invites() -> list[dict]:
    rows = _req("GET", "/rest/v1/voice_invites?select=id,speaker_id,speaker_name,consent_at,active,created_at"
                       "&order=created_at.desc")
    ups = _req("GET", "/rest/v1/voice_uploads?select=invite_id,duration,synced")
    out = []
    for r in rows:
        mine = [u for u in ups if u["invite_id"] == r["id"]]
        out.append({**r, "uploads": len(mine), "seconds": round(sum(u["duration"] or 0 for u in mine), 1),
                    "pending": sum(1 for u in mine if not u["synced"])})
    return out


def deactivate(invite_id: str):
    _req("PATCH", f"/rest/v1/voice_invites?id=eq.{urllib.parse.quote(invite_id)}", {"active": False},
         expect_json=False)


def _ensure_local_speaker(inv: dict):
    spk = voice._load_speakers()
    if any(s["id"] == inv["speaker_id"] for s in spk):
        return
    spk.append({"id": inv["speaker_id"], "name": inv.get("speaker_name") or inv["speaker_id"],
                "role": "qoʻshimcha ovoz (masofadan)",
                "consent": {"text": inv.get("consent_text") or voice.CONSENT_TEXT,
                            "date": inv.get("consent_at") or datetime.now().isoformat(timespec="seconds"),
                            "source": "remote"}})
    (voice.VDIR / "speakers.json").write_text(json.dumps(spk, ensure_ascii=False, indent=1), encoding="utf-8")


def sync() -> dict:
    if not configured():
        return {"error": "Supabase sozlanmagan"}
    rows = _req("GET", "/rest/v1/voice_uploads?select=*&synced=eq.false&order=id.asc&limit=200")
    if not rows:
        return {"new": 0, "saved": 0, "rejected": 0}
    invites = {i["id"]: i for i in _req("GET", "/rest/v1/voice_invites?select=*")}
    saved = rejected = 0
    errors = []
    for row in rows:
        inv = invites.get(row["invite_id"])
        if not inv or not inv.get("consent_at"):
            continue
        _ensure_local_speaker(inv)
        try:
            audio = _req("GET", f"/storage/v1/object/voice/{urllib.parse.quote(row['path'])}", expect_json=False)
            if row["item_id"].startswith("p"):
                res = voice.save_paragraph(row["item_id"], audio, row.get("marks"), speaker=inv["speaker_id"])
                ok = res.get("ok") and not res.get("warnings")
            else:
                rec = voice.save_recording(row["item_id"], audio, speaker=inv["speaker_id"])
                ok = voice.is_usable(rec)
            saved += bool(ok)
            rejected += not ok
        except Exception as ex:
            errors.append(f"{row['item_id']}: {ex}")
            rejected += 1
        _req("PATCH", f"/rest/v1/voice_uploads?id=eq.{row['id']}", {"synced": True}, expect_json=False)
    return {"new": len(rows), "saved": saved, "rejected": rejected, "errors": errors[:5]}
