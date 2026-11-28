import { AnimatePresence, motion } from "motion/react";
import { Check, CheckCircle2, ChevronDown, Mic, Play, Plus, RotateCcw, SkipForward, Square, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { RemotePanel } from "./RemotePanel";

type Item = { id: string; text?: string; sentences?: string[] };
type VState = {
  speaker: string; mode: "sentence" | "paragraph"; total: number; done_items: number; recorded: number;
  seconds: number; goal_seconds: number; next: Item | null; with_warnings: number;
};
type Speaker = { id: string; name: string; role: string; recorded: number; seconds: number };
type Result = {
  ok: boolean; id: string; error?: string; duration?: number; warnings?: string[];
  rms_db?: number; snr_db?: number; segments?: { id: string; duration: number }[];
};

const CONSENT = "Men ushbu ovoz yozuvlarimni OMZU sunʼiy intellekt modelini oʻqitish va OMZU mahsulotida ovoz sifatida ishlatish uchun ixtiyoriy ravishda beraman.";

function encodeWav(chunks: Float32Array[], sr: number): Blob {
  const len = chunks.reduce((a, c) => a + c.length, 0);
  const buf = new ArrayBuffer(44 + len * 2);
  const v = new DataView(buf);
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + len * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, len * 2, true);
  let o = 44;
  for (const c of chunks) for (let i = 0; i < c.length; i++, o += 2) {
    const s = Math.max(-1, Math.min(1, c[i]));
    v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

const BARS = 32;

export function Recorder({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [speaker, setSpeaker] = useState("ozodbek");
  const [mode, setMode] = useState<"sentence" | "paragraph">("sentence");
  const [st, setSt] = useState<VState | null>(null);
  const [phase, setPhase] = useState<"idle" | "recording" | "saving">("idle");
  const [cur, setCur] = useState(0);
  const [levels, setLevels] = useState<number[]>(Array(BARS).fill(0));
  const [last, setLast] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [menu, setMenu] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [consent, setConsent] = useState(false);
  const ctx = useRef<AudioContext | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Float32Array[]>([]);
  const samples = useRef(0);
  const marks = useRef<number[]>([]);
  const proc = useRef<ScriptProcessorNode | null>(null);
  const raf = useRef(0);
  const starting = useRef(false);

  const loadSpeakers = useCallback(() => fetch("/api/voice/speakers").then((r) => r.json()).then(setSpeakers), []);
  const load = useCallback(() =>
    fetch(`/api/voice/state?speaker=${speaker}&mode=${mode}`).then((r) => r.json()).then(setSt), [speaker, mode]);
  useEffect(() => { if (open) { loadSpeakers(); load(); setLast(null); setErr(null); } }, [open, load, loadSpeakers]);

  const stopAudio = () => {
    cancelAnimationFrame(raf.current);
    if (proc.current) proc.current.onaudioprocess = null;
    proc.current?.disconnect();
    stream.current?.getTracks().forEach((t) => t.stop());
    ctx.current?.close();
    ctx.current = null; stream.current = null; proc.current = null;
    setLevels(Array(BARS).fill(0));
  };
  useEffect(() => () => stopAudio(), []);

  const sentences = st?.next ? (st.next.sentences ?? [st.next.text ?? ""]) : [];

  const start = async () => {
    if (starting.current || ctx.current) return;
    starting.current = true;
    setErr(null); setLast(null);
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
      const ac = new AudioContext();
      const src = ac.createMediaStreamSource(s);
      const an = ac.createAnalyser(); an.fftSize = 256;
      const p = ac.createScriptProcessor(4096, 1, 1);
      const buf: Float32Array[] = [];
      chunks.current = buf; samples.current = 0; marks.current = [];
      p.onaudioprocess = (e) => {
        if (chunks.current !== buf) return;
        const d = new Float32Array(e.inputBuffer.getChannelData(0));
        buf.push(d); samples.current += d.length;
      };
      src.connect(an); src.connect(p); p.connect(ac.destination);
      ctx.current = ac; stream.current = s; proc.current = p;
      const data = new Uint8Array(an.frequencyBinCount);
      const tick = () => {
        an.getByteFrequencyData(data);
        setLevels(Array.from({ length: BARS }, (_, i) => data[Math.floor((i / BARS) * data.length * 0.7)] / 255));
        raf.current = requestAnimationFrame(tick);
      };
      tick();
      setCur(0);
      setPhase("recording");
    } catch {
      setErr("Mikrofonga ruxsat berilmadi. Brauzer manzil satridagi 🔒 belgisini bosib, mikrofonga ruxsat bering.");
    } finally {
      starting.current = false;
    }
  };

  const stop = async () => {
    if (!ctx.current || !st?.next) return;
    const sr = ctx.current.sampleRate;
    const wav = encodeWav(chunks.current, sr);
    stopAudio();
    setPhase("saving");
    const fd = new FormData();
    fd.append("sid", st.next.id);
    fd.append("speaker", speaker);
    fd.append("marks", JSON.stringify(marks.current));
    fd.append("audio", wav, `${st.next.id}.wav`);
    try {
      const r = await fetch("/api/voice/record", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail);
      setLast(j.result);
      if (j.result.ok) { setSt(j.state); loadSpeakers(); }
    } catch (e) {
      setErr(String((e as Error).message || e));
    }
    setPhase("idle");
  };

  const space = () => {
    if (phase === "idle") return start();
    if (phase !== "recording") return;
    if (cur < sentences.length - 1 && ctx.current) {
      marks.current.push(samples.current / ctx.current.sampleRate);
      setCur((c) => c + 1);
    } else {
      stop();
    }
  };

  const skip = async () => {
    if (!st?.next) return;
    setSt(await (await fetch(`/api/voice/skip/${st.next.id}?speaker=${speaker}`, { method: "POST" })).json());
    setLast(null);
  };
  const redo = async () => {
    if (!last?.ok) return;
    setSt(await (await fetch(`/api/voice/record/${last.id}?speaker=${speaker}`, { method: "DELETE" })).json());
    setLast(null); loadSpeakers();
  };
  const play = () => { if (last?.ok) new Audio(`/api/voice/audio/${speaker}/${last.id}?t=${Date.now()}`).play(); };

  const addSpeaker = async () => {
    const r = await fetch("/api/voice/speakers", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName, consent }),
    });
    const j = await r.json();
    if (!r.ok) { setErr(j.detail); return; }
    setAdding(false); setNewName(""); setConsent(false); setMenu(false);
    await loadSpeakers(); setSpeaker(j.id);
  };

  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "TEXTAREA" || tag === "INPUT") return;
      if (e.code === "Space") { e.preventDefault(); (document.activeElement as HTMLElement)?.blur?.(); if (!e.repeat) space(); }
      else if (e.key.toLowerCase() === "r" && phase === "idle") redo();
      else if (e.key.toLowerCase() === "s" && phase === "idle") skip();
      else if (e.key.toLowerCase() === "p" && phase === "idle") play();
      else if (e.key === "Escape" && phase !== "recording") onClose();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  const pct = st ? Math.min(100, (st.seconds / st.goal_seconds) * 100) : 0;
  const spk = speakers.find((s) => s.id === speaker);
  const isPara = mode === "paragraph";
  const lastSentence = phase === "recording" && cur === sentences.length - 1;

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex flex-col bg-bg" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="flex flex-wrap items-center gap-3 px-6 pt-5">
            <div className="text-lg font-semibold">🎙 Ovoz yozish</div>

            <div className="relative">
              <button onClick={() => phase === "idle" && setMenu((m) => !m)}
                className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-1.5 text-sm transition hover:border-line-strong">
                <span className="bg-grad grid h-6 w-6 place-items-center rounded-full text-[11px] font-bold text-white">{spk?.name?.[0] ?? "?"}</span>
                {spk?.name ?? speaker}
                <ChevronDown size={15} className="text-muted" />
              </button>
              <AnimatePresence>
                {menu && (
                  <motion.div initial={{ opacity: 0, y: -6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6 }}
                    className="absolute left-0 top-11 z-10 w-[330px] rounded-2xl border border-line bg-surface p-2 shadow-float">
                    {speakers.map((s) => (
                      <button key={s.id} onClick={() => { setSpeaker(s.id); setMenu(false); setLast(null); }}
                        className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition hover:bg-surface-2">
                        <span className="bg-grad grid h-7 w-7 place-items-center rounded-full text-xs font-bold text-white">{s.name[0]}</span>
                        <span className="flex-1"><span className="block text-sm">{s.name}</span>
                          <span className="text-xs text-muted">{s.role} · {Math.floor(s.seconds / 60)} daq · {s.recorded} yozuv</span></span>
                        {s.id === speaker && <Check size={16} className="text-accent" />}
                      </button>
                    ))}
                    {!adding ? (
                      <button onClick={() => setAdding(true)} className="mt-1 flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-sm text-accent transition hover:bg-surface-2">
                        <Plus size={16} /> Yangi diktor qoʻshish
                      </button>
                    ) : (
                      <div className="mt-1 grid gap-2 rounded-xl bg-surface-2 p-3">
                        <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Ism familiya"
                          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent" />
                        <label className="flex cursor-pointer gap-2 text-xs leading-snug text-muted">
                          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 accent-[#6d5dfc]" />
                          <span><b className="text-fg">Diktor roziligi:</b> «{CONSENT}» — buni diktorning oʻzi tasdiqlashi kerak.</span>
                        </label>
                        <div className="flex justify-end gap-2">
                          <button onClick={() => setAdding(false)} className="rounded-lg px-3 py-1 text-sm text-muted hover:text-fg">Bekor</button>
                          <button disabled={!newName.trim() || !consent} onClick={addSpeaker}
                            className="bg-grad rounded-lg px-3 py-1 text-sm font-medium text-white disabled:opacity-40">Qoʻshish</button>
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {phase === "idle" && <RemotePanel onSynced={loadSpeakers} />}

            <div className="relative flex rounded-xl border border-line bg-surface p-0.5 text-sm">
              {(["sentence", "paragraph"] as const).map((m) => (
                <button key={m} disabled={phase !== "idle"} onClick={() => { setMode(m); setLast(null); }}
                  className={`relative z-10 rounded-[10px] px-3 py-1 transition-colors ${mode === m ? "text-white" : "text-muted hover:text-fg"}`}>
                  {mode === m && <motion.span layoutId="mode-pill" className="bg-grad absolute inset-0 -z-10 rounded-[10px]" />}
                  {m === "sentence" ? "Gaplar" : "Matnlar"}
                </button>
              ))}
            </div>

            <div className="min-w-[200px] flex-1">
              <div className="h-2 overflow-hidden rounded-full bg-surface-2">
                <motion.div className="bg-grad h-full rounded-full" animate={{ width: `${pct}%` }} transition={{ type: "spring", stiffness: 120, damping: 20 }} />
              </div>
              <div className="mt-1 text-xs text-muted">
                {st ? Math.floor(st.seconds / 60) : 0} / {st ? st.goal_seconds / 60 : 60} daqiqa · {st?.recorded ?? 0} ta gap
                {st && st.with_warnings > 0 && <span className="text-amber-500"> · {st.with_warnings} ta sifatsiz yozuv hisoblanmadi (keyinroq qayta taklif qilinadi)</span>}
              </div>
            </div>
            <button onClick={() => phase !== "recording" && onClose()} className="grid h-9 w-9 place-items-center rounded-xl text-muted transition hover:bg-surface-2 hover:text-fg"><X size={20} /></button>
          </div>

          <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-6" onClick={() => setMenu(false)}>
            {st?.next ? (
              <AnimatePresence mode="wait">
                <motion.div key={st.next.id}
                  initial={{ opacity: 0, y: 20, filter: "blur(6px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                  exit={{ opacity: 0, y: -20, filter: "blur(6px)" }} transition={{ duration: 0.35 }}
                  className={`max-w-3xl text-center font-medium leading-snug ${isPara ? "text-[clamp(19px,2.3vw,25px)]" : "text-[clamp(22px,3.2vw,34px)]"}`}>
                  {isPara ? sentences.map((s, i) => {
                    const active = phase === "recording" && i === cur;
                    const done = phase === "recording" && i < cur;
                    return (
                      <motion.span key={i}
                        animate={{ opacity: phase !== "recording" || active ? 1 : done ? 0.3 : 0.5 }}
                        className={`rounded-lg px-1 transition-colors duration-300 ${active ? "bg-accent/12 text-fg" : ""}`}>
                        {s}{" "}
                      </motion.span>
                    );
                  }) : st.next.text}
                </motion.div>
              </AnimatePresence>
            ) : (
              <div className="text-center text-xl text-muted">{st ? "🎉 Bu boʻlimdagi hamma matnlar yozildi! Rahmat." : "Yuklanmoqda…"}</div>
            )}

            <div className="mt-10 flex h-16 items-end gap-[3px]">
              {levels.map((l, i) => (
                <motion.div key={i} className={`w-[6px] rounded-full ${phase === "recording" ? "bg-grad" : "bg-line-strong"}`}
                  animate={{ height: 6 + l * 58 }} transition={{ duration: 0.08 }} />
              ))}
            </div>

            <div className="mt-7 flex items-center gap-4">
              <button onMouseDown={(e) => e.preventDefault()} onClick={skip} disabled={phase !== "idle"} title="Oʻtkazib yuborish (S)"
                className="grid h-12 w-12 place-items-center rounded-full border border-line text-muted transition hover:bg-surface-2 hover:text-fg disabled:opacity-40"><SkipForward size={19} /></button>
              <motion.button whileTap={{ scale: 0.92 }} onMouseDown={(e) => e.preventDefault()} onClick={phase === "recording" ? (isPara && !lastSentence ? space : stop) : start}
                disabled={phase === "saving" || !st?.next}
                className={`relative grid h-20 w-20 place-items-center rounded-full text-white shadow-float transition disabled:opacity-50 ${phase === "recording" ? "bg-rose-500" : "bg-grad"}`}
                title="Probel">
                {phase === "recording" && <motion.span className="absolute inset-0 rounded-full bg-rose-500" animate={{ scale: [1, 1.35], opacity: [0.5, 0] }} transition={{ repeat: Infinity, duration: 1.2 }} />}
                {phase === "recording"
                  ? (isPara && !lastSentence ? <SkipForward size={26} className="relative" /> : <Square size={26} fill="currentColor" className="relative" />)
                  : <Mic size={30} className="relative" />}
              </motion.button>
              <button onMouseDown={(e) => e.preventDefault()} onClick={play} disabled={!last?.ok || phase !== "idle"} title="Oxirgi yozuvni tinglash (P)"
                className="grid h-12 w-12 place-items-center rounded-full border border-line text-muted transition hover:bg-surface-2 hover:text-fg disabled:opacity-40"><Play size={19} /></button>
            </div>
            <div className="mt-3 max-w-xl text-center text-sm text-faint">
              {phase === "saving" ? "Saqlanmoqda…"
                : phase === "recording"
                  ? (isPara
                    ? (lastSentence ? "Oxirgi gap — tugatgach Probel: yozish toʻxtaydi" : `${cur + 1}/${sentences.length}-gap · tugatgach Probel, keyin qisqa pauza qilib keyingisini oʻqing`)
                    : "Yozilmoqda… tugatgach Probel")
                  : isPara
                    ? "Probel — boshlash. Har gapni tugatgach Probelni bosing (yorituvchi keyingi gapga oʻtadi)."
                    : "Probel — yozish · S — oʻtkazish · P — tinglash · R — qayta yozish"}
            </div>

            <AnimatePresence>
              {last && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                  className={`mt-6 flex max-w-xl items-start gap-3 rounded-2xl border px-4 py-3 text-sm ${!last.ok ? "border-rose-500/40 bg-rose-500/8" : last.warnings?.length ? "border-amber-500/40 bg-amber-500/8" : "border-emerald-500/40 bg-emerald-500/8"}`}>
                  {!last.ok || last.warnings?.length ? <TriangleAlert size={18} className={`mt-0.5 flex-none ${last.ok ? "text-amber-500" : "text-rose-500"}`} /> : <CheckCircle2 size={18} className="mt-0.5 flex-none text-emerald-500" />}
                  <div className="flex-1">
                    {!last.ok ? <><b>Saqlanmadi.</b> {last.error}</> : <>
                      <b>{last.warnings?.length ? "Hisoblanmadi — qayta yozing (R):" : isPara ? `Ajoyib — ${last.segments?.length} ta gapga ajratildi!` : "Ajoyib — sifati yaxshi!"}</b>
                      {last.warnings?.map((w) => <div key={w}>• {w}</div>)}
                      <div className="mt-1 text-xs text-muted">{last.duration} s · balandlik {last.rms_db} dB · shovqindan ustunlik {last.snr_db} dB</div>
                    </>}
                  </div>
                  {last.ok && <button onClick={redo} title="Qayta yozish (R)" className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-muted transition hover:bg-surface-2 hover:text-fg"><RotateCcw size={13} /> Qayta</button>}
                </motion.div>
              )}
            </AnimatePresence>
            {err && <div className="mt-6 max-w-xl rounded-2xl border border-rose-500/40 bg-rose-500/8 px-4 py-3 text-sm">{err}</div>}
          </div>

          <div className="px-6 pb-6 text-center text-xs text-faint">
            Maslahat: tinch xonada, mikrofondan bir xil masofada, shoshilmasdan va tabiiy ohangda (kimgadir tushuntirayotgandek) oʻqing.
            Har bir odam faqat <b>oʻz nomi</b> ostida yozsin — ovozlar aralashmasligi kerak.
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
