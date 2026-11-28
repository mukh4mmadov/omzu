import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
API = "https://api.supabase.com/v1"


def env() -> dict:
    out = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def set_env(key: str, value: str):
    lines = ENV.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith(key + "="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def call(method: str, path: str, body=None, base: str = API, token: str | None = None, headers: dict | None = None):
    token = token or env()["SUPABASE_ACCESS_TOKEN"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        "User-Agent": "omzu-setup/0.1", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Supabase xatosi {e.code}: {e.read().decode()[:500]}") from e


def main():
    cmd = sys.argv[1]
    if cmd == "projects":
        for p in call("GET", "/projects"):
            print(f"{p['name']:20s} ref={p['id']}  region={p['region']}  status={p['status']}")
    elif cmd == "keys":
        ref = sys.argv[2]
        keys = call("GET", f"/projects/{ref}/api-keys?reveal=true")
        found = {}
        for k in keys:
            name, typ = k.get("name", ""), k.get("type", "")
            if typ == "secret" or name == "service_role":
                found.setdefault("SUPABASE_SECRET_KEY", k["api_key"])
            if typ == "publishable" or name == "anon":
                found.setdefault("SUPABASE_PUBLISHABLE_KEY", k["api_key"])
        set_env("SUPABASE_URL", f"https://{ref}.supabase.co")
        set_env("SUPABASE_REF", ref)
        for k, v in found.items():
            set_env(k, v)
        print("Yozildi .env ga:", ", ".join(["SUPABASE_URL", "SUPABASE_REF", *found]))
    elif cmd == "sql":
        ref, f = sys.argv[2], sys.argv[3]
        res = call("POST", f"/projects/{ref}/database/query", {"query": Path(f).read_text(encoding="utf-8")})
        print(json.dumps(res, ensure_ascii=False)[:800])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
