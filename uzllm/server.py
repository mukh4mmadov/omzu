import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from uzllm import assistant, documents, remote_voice, tools, voice
from uzllm.storage import SQLiteStore, new_id

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DIST = WEB / "dist"

app = FastAPI(title="OMZU")
store = SQLiteStore()
USER = "local"

if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


class ChatIn(BaseModel):
    message: str
    conversation_id: str | None = None


class FeedbackIn(BaseModel):
    message_id: str
    rating: int
    correction: str | None = None


@app.get("/")
def index():
    return FileResponse(DIST / "index.html" if (DIST / "index.html").exists() else WEB / "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(DIST / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(DIST / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


if (DIST / "icons").exists():
    app.mount("/icons", StaticFiles(directory=DIST / "icons"), name="icons")


@app.get("/api/status")
def status():
    return assistant.model_status()


def _sse(obj) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
def chat(body: ChatIn):
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "bo'sh xabar")
    cid = store.ensure_conversation(body.conversation_id, text, USER)
    user_mid = store.add_message(cid, "user", text)
    history = store.history(cid)
    bot_mid = new_id()

    def events():
        yield _sse({"type": "meta", "conversation_id": cid, "message_id": bot_mid, "user_message_id": user_mid})
        full, extra = "", {"tools": [], "sources": []}
        try:
            for ev in assistant.respond(history):
                if ev["type"] == "token":
                    full += ev["text"]
                elif ev["type"] == "tool":
                    extra["tools"].append(ev)
                elif ev["type"] == "sources":
                    extra["sources"] = ev["items"]
                yield _sse(ev)
        except Exception as e:
            msg = f"\n\n⚠️ Ichki xato: {e}"
            full += msg
            yield _sse({"type": "token", "text": msg})
            yield _sse({"type": "done"})
        finally:
            store.add_message(cid, "assistant", full, extra, mid=bot_mid)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/conversations")
def conversations():
    return store.list_conversations(USER)


@app.get("/api/conversations/{cid}")
def conversation(cid: str):
    return store.messages(cid, USER)


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: str):
    store.delete_conversation(cid, USER)
    return {"ok": True}


@app.post("/api/feedback")
def feedback(body: FeedbackIn):
    store.save_feedback(body.message_id, body.rating, body.correction, USER)
    return {"ok": True}


@app.post("/api/documents")
async def upload_documents(files: list[UploadFile] = File(...)):
    results = []
    for f in files:
        try:
            info = await run_in_threadpool(documents.add_file, f.filename or "fayl.txt", await f.read())
            results.append({"ok": True, **info})
        except Exception as e:
            results.append({"ok": False, "name": f.filename, "error": str(e)})
    return results


@app.get("/api/documents")
def list_documents():
    return documents.list_files()


@app.delete("/api/documents/{name}")
def delete_document(name: str):
    return {"deleted": documents.delete_file(name)}


def _voice(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _mode(item_id: str) -> str:
    return "paragraph" if item_id.startswith("p") else "sentence"


@app.get("/api/voice/speakers")
def voice_speakers():
    return voice.list_speakers()


class SpeakerIn(BaseModel):
    name: str
    consent: bool


@app.post("/api/voice/speakers")
def voice_add_speaker(body: SpeakerIn):
    return _voice(voice.add_speaker, body.name, body.consent)


@app.get("/api/voice/state")
def voice_state(speaker: str = voice.DEFAULT_SPEAKER, mode: str = "sentence"):
    return _voice(voice.state, speaker, mode)


@app.post("/api/voice/record")
async def voice_record(sid: str = Form(...), audio: UploadFile = File(...),
                       speaker: str = Form(voice.DEFAULT_SPEAKER), marks: str = Form("")):
    data = await audio.read()
    try:
        if sid.startswith("p"):
            mk = [float(v) for v in json.loads(marks)] if marks else None
            res = await run_in_threadpool(voice.save_paragraph, sid, data, mk, speaker)
        else:
            rec = await run_in_threadpool(voice.save_recording, sid, data, speaker)
            res = {"ok": True, "id": sid, "segments": [{"id": sid, "duration": rec["duration"]}], **rec}
    except Exception as e:
        raise HTTPException(400, f"yozuvni saqlab boʻlmadi: {e}") from e
    return {"result": res, "state": voice.state(speaker, _mode(sid))}


class InviteIn(BaseModel):
    note: str = ""


@app.get("/api/voice/invites")
def voice_invites():
    if not remote_voice.configured():
        return {"configured": False, "invites": []}
    return {"configured": True, "invites": remote_voice.list_invites()}


@app.post("/api/voice/invites")
async def voice_create_invite(body: InviteIn):
    if not remote_voice.configured():
        raise HTTPException(400, "Supabase sozlanmagan")
    return await run_in_threadpool(remote_voice.create_invite, body.note)


@app.delete("/api/voice/invites/{invite_id}")
async def voice_deactivate_invite(invite_id: str):
    await run_in_threadpool(remote_voice.deactivate, invite_id)
    return {"ok": True}


@app.post("/api/voice/sync")
async def voice_sync():
    if not remote_voice.configured():
        raise HTTPException(400, "Supabase sozlanmagan")
    return await run_in_threadpool(remote_voice.sync)


@app.post("/api/voice/skip/{sid}")
def voice_skip(sid: str, speaker: str = voice.DEFAULT_SPEAKER):
    _voice(voice.skip, sid, speaker)
    return voice.state(speaker, _mode(sid))


@app.delete("/api/voice/record/{sid}")
def voice_delete(sid: str, speaker: str = voice.DEFAULT_SPEAKER):
    _voice(voice.delete, sid, speaker)
    return voice.state(speaker, _mode(sid))


@app.get("/api/voice/audio/{speaker}/{sid}")
def voice_audio(speaker: str, sid: str):
    p = _voice(voice.audio_path, sid, speaker)
    if not p:
        raise HTTPException(404)
    return FileResponse(p, media_type="audio/wav", headers={"Cache-Control": "no-cache"})


class TaskIn(BaseModel):
    text: str
    due: str | None = None


@app.get("/api/tasks")
def list_tasks(all: bool = True):
    return tools.list_tasks(include_done=all)["tasks"]


@app.post("/api/tasks")
def add_task(body: TaskIn):
    return tools.add_task(body.text, body.due)


@app.post("/api/tasks/{tid}/toggle")
def toggle_task(tid: int, done: bool = True):
    return tools.complete_task(id=tid, done=done)


@app.delete("/api/tasks/{tid}")
def delete_task(tid: int):
    return tools.delete_task(tid)


@app.get("/api/reminders/due")
def reminders_due():
    return tools.due_reminders()


@app.get("/api/reminders")
def reminders():
    return tools.list_reminders()["reminders"]


@app.get("/api/memories")
def memories():
    return tools.list_memories()["memories"]


@app.delete("/api/memories/{mid}")
def delete_memory(mid: int):
    return tools.forget(mid)


def main():
    import uvicorn
    print("OMZU ishga tushdi:  http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
