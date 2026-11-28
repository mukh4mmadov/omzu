import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, Mic, SkipForward, Square, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { encodeWav, openMic, quickQC, type Mic as MicT, type QC } from "../audio";
import { Orb } from "../components/Orb";

const FN = `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/voice`;
const KEY = import.meta.env.VITE_SUPABASE_KEY as string;
const GOAL_MIN = 30;
const BARS = 28;

type Item = { id: string; text?: string; sentences?: string[] };
type Session = { name: string | null; consent: boolean; consent_text: string; done: string[]; seconds: number };

async function call(body: Record<string, unknown>) {
  const r = await fetch(FN, { method: "POST", headers: { "Content-Type": "application/json", apikey: KEY }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || `xato ${r.status}`);
  return j;
}

export function RemoteRecorder() {
  const token = new URLSearchParams(location.hash.slice(1)).get("t") ?? "";
  const [sess, setSess] = useState<Session | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [agree, setAgree] = useState(false);
  const [mode, setMode] = useState<"sentence" | "paragraph">("sentence");
  const [items, setItems] = useState<{ sentence: Item[]; paragraph: Item[] }>({ sentence: [], paragraph: [] });
  const [skipped, setSkipped] = useState<string[]>([]);
  const [phase, setPhase] = useState<"idle" | "recording" | "uploading">("idle");
  const [cur, setCur] = useState(0);
  const [levels, setLevels] = useState<number[]>(Array(BARS).fill(0));
  const [qc, setQc] = useState<QC | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const mic = useRef<MicT | null>(null);
  const marks = useRef<number[]>([]);
  const raf = useRef(0);
  const busy = useRef(false);

  const load = useCallback(async () => {
    if (!token) { setFatal("Havola notoʻgʻri — taklif qilgan odamdan toʻliq havolani soʻrang."); return; }
    try { setSess(await call({ action: "session", token })); } catch (e) { setFatal((e as Error).message); }
  }, [token]);

  useEffect(() => {
    load();
    Promise.all([fetch("/voice/script.json").then((r) => r.json()), fetch("/voice/paragraphs.json").then((r) => r.json())])
      .then(([s, p]) => setItems({ sentence: s, paragraph: p }));
    try { setSkipped(JSON.parse(localStorage.getItem("omzu-skip") || "[]")); } catch {  }
  }, [load]);

  const done = new Set(sess?.done ?? []);
  const next = items[mode].find((i) => !done.has(i.id) && !skipped.includes(i.id)) ?? null;
  const sentences = next ? (next.sentences ?? [next.text ?? ""]) : [];
  const isPara = mode === "paragraph";
  const lastSentence = phase === "recording" && cur === sentences.length - 1;

  const start = async () => {
    if (busy.current || mic.current || !next) return;
    busy.current = true;
    setQc(null); setMsg(null);
    try {
      mic.current = await openMic(BARS);
      marks.current = [];
      const tick = () => { if (mic.current) setLevels(mic.current.level()); raf.current = requestAnimationFrame(tick); };
      tick();
      setCur(0); setPhase("recording");
    } catch {
      setMsg("Mikrofonga ruxsat berilmadi. Brauzer sozlamalarida bu sayt uchun mikrofonga ruxsat bering.");
    } finally { busy.current = false; }
  };

  const stop = async () => {
    const m = mic.current;
    if (!m || !next) return;
    cancelAnimationFrame(raf.current);
    mic.current = null;
    m.stop();
    setLevels(Array(BARS).fill(0));
    const sr = m.ctx.sampleRate;
    const q = quickQC(m.buf, sr);
    setQc(q);
    if (q.warnings.length) { setPhase("idle"); return; }
    setPhase("uploading");
    try {
      const u = await call({ action: "upload_url", token, item_id: next.id });
      const put = await fetch(u.signedUrl, { method: "PUT", headers: { "Content-Type": "audio/wav" }, body: encodeWav(m.buf, sr) });
      if (!put.ok) throw new Error("fayl yuklanmadi");
      await call({ action: "commit", token, item_id: next.id, path: u.path, marks: marks.current, duration: q.duration, qc: q });
      setSess((s) => s && { ...s, done: [...s.done, next.id], seconds: s.seconds + q.duration });
    } catch (e) {
      setMsg(`Yuborib boʻlmadi: ${(e as Error).message}. Internetni tekshirib, qayta yozing.`);
    }
    setPhase("idle");
  };

  const advance = () => {
    if (phase === "idle") return start();
    if (phase !== "recording") return;
    if (isPara && cur < sentences.length - 1 && mic.current) {
      marks.current.push(mic.current.samples() / mic.current.ctx.sampleRate);
      setCur((c) => c + 1);
    } else stop();
  };

  const skip = () => {
    if (!next || phase !== "idle") return;
    const s = [...skipped, next.id];
    setSkipped(s); setQc(null);
    try { localStorage.setItem("omzu-skip", JSON.stringify(s)); } catch {  }
  };

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.code === "Space" && sess?.consent) { e.preventDefault(); (document.activeElement as HTMLElement)?.blur?.(); if (!e.repeat) advance(); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  const giveConsent = async () => {
    try { await call({ action: "consent", token, name: name.trim(), agree: true }); await load(); }
    catch (e) { setMsg((e as Error).message); }
  };

  if (fatal) return <Center><TriangleAlert className="mx-auto mb-3 text-rose-500" size={36} /><p className="text-lg">{fatal}</p></Center>;
  if (!sess) return <Center><Orb size={64} busy /><p className="mt-4 text-muted">Yuklanmoqda…</p></Center>;

  if (!sess.consent) {
    return (
      <Center>
        <motion.div initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="mx-auto w-fit"><Orb size={84} glow /></motion.div>
        <h1 className="mt-6 text-2xl font-semibold">Assalomu alaykum! 👋</h1>
        <p className="mx-auto mt-2 max-w-md text-muted">
          Sizni <b className="text-fg">OMZU</b> — oʻzbekcha sunʼiy intellekt yordamchisining ovozini yaratishga taklif qilishdi.
          Ekranda chiqqan gaplarni ovoz chiqarib oʻqiysiz, xolos. Kuniga 10–15 daqiqa yetarli.
        </p>
        <div className="mx-auto mt-6 grid max-w-md gap-3 text-left">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ismingiz va familiyangiz"
            className="rounded-xl border border-line bg-surface px-4 py-3 outline-none focus:border-accent" />
          <label className="flex cursor-pointer gap-3 rounded-xl border border-line bg-surface p-4 text-sm leading-relaxed">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1 h-4 w-4 accent-[#6d5dfc]" />
            <span>{sess.consent_text}</span>
          </label>
          <button disabled={!name.trim() || !agree} onClick={giveConsent}
            className="bg-grad rounded-xl py-3 font-semibold text-white transition disabled:opacity-40">Roziman, boshlaymiz</button>
          {msg && <p className="text-sm text-rose-500">{msg}</p>}
        </div>
      </Center>
    );
  }

  const minutes = Math.floor(sess.seconds / 60);
  return (
    <div className="flex min-h-dvh flex-col">
      <div className="flex flex-wrap items-center gap-3 px-5 pt-4">
        <Orb size={30} />
        <div className="text-[15px] font-semibold">OMZU ovozi · {sess.name}</div>
        <div className="flex rounded-xl border border-line bg-surface p-0.5 text-sm">
          {(["sentence", "paragraph"] as const).map((m) => (
            <button key={m} disabled={phase !== "idle"} onClick={() => { setMode(m); setQc(null); }}
              className={`relative z-10 rounded-[10px] px-3 py-1 ${mode === m ? "text-white" : "text-muted"}`}>
              {mode === m && <motion.span layoutId="rmode" className="bg-grad absolute inset-0 -z-10 rounded-[10px]" />}
              {m === "sentence" ? "Gaplar" : "Matnlar"}
            </button>
          ))}
        </div>
        <div className="min-w-[160px] flex-1">
          <div className="h-2 overflow-hidden rounded-full bg-surface-2">
            <motion.div className="bg-grad h-full" animate={{ width: `${Math.min(100, (sess.seconds / 60 / GOAL_MIN) * 100)}%` }} />
          </div>
          <div className="mt-1 text-xs text-muted">{minutes} / {GOAL_MIN} daqiqa · {sess.done.length} ta yozuv · rahmat! 🙏</div>
        </div>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center px-5 py-6 text-center">
        {next ? (
          <AnimatePresence mode="wait">
            <motion.div key={next.id} initial={{ opacity: 0, y: 16, filter: "blur(6px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -16, filter: "blur(6px)" }}
              className={`max-w-3xl font-medium leading-snug ${isPara ? "text-[clamp(18px,4.6vw,25px)]" : "text-[clamp(21px,5.4vw,34px)]"}`}>
              {isPara ? sentences.map((s, i) => (
                <motion.span key={i} animate={{ opacity: phase !== "recording" || i === cur ? 1 : i < cur ? 0.3 : 0.5 }}
                  className={`rounded-lg px-1 ${phase === "recording" && i === cur ? "bg-accent/12" : ""}`}>{s}{" "}</motion.span>
              )) : next.text}
            </motion.div>
          </AnimatePresence>
        ) : <p className="text-xl text-muted">🎉 Hammasi yozildi! Katta rahmat.</p>}

        <div className="mt-8 flex h-14 items-end gap-[3px]">
          {levels.map((l, i) => <motion.div key={i} className={`w-[5px] rounded-full ${phase === "recording" ? "bg-grad" : "bg-line-strong"}`} animate={{ height: 5 + l * 50 }} transition={{ duration: 0.08 }} />)}
        </div>

        <div className="mt-6 flex items-center gap-5">
          <button onMouseDown={(e) => e.preventDefault()} onClick={skip} disabled={phase !== "idle"} title="Oʻtkazish"
            className="grid h-12 w-12 place-items-center rounded-full border border-line text-muted disabled:opacity-40"><SkipForward size={19} /></button>
          <motion.button whileTap={{ scale: 0.92 }} onMouseDown={(e) => e.preventDefault()} onClick={advance}
            disabled={phase === "uploading" || !next}
            className={`relative grid h-20 w-20 place-items-center rounded-full text-white shadow-float disabled:opacity-50 ${phase === "recording" ? "bg-rose-500" : "bg-grad"}`}>
            {phase === "recording" && <motion.span className="absolute inset-0 rounded-full bg-rose-500" animate={{ scale: [1, 1.35], opacity: [0.5, 0] }} transition={{ repeat: Infinity, duration: 1.2 }} />}
            {phase === "recording" ? (isPara && !lastSentence ? <SkipForward size={26} className="relative" /> : <Square size={26} fill="currentColor" className="relative" />) : <Mic size={30} className="relative" />}
          </motion.button>
          <div className="h-12 w-12" />
        </div>
        <p className="mt-3 max-w-md text-sm text-faint">
          {phase === "uploading" ? "Yuborilmoqda…"
            : phase === "recording" ? (isPara ? (lastSentence ? "Oxirgi gap — tugatgach tugmani bosing" : `${cur + 1}/${sentences.length}-gap · tugatgach tugmani bosing (yoki Probel)`) : "Oʻqib boʻlgach tugmani bosing (yoki Probel)")
            : "Tugmani bosing (yoki Probel) va matnni tabiiy ohangda oʻqing"}
        </p>

        <AnimatePresence>
          {qc && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className={`mt-5 flex max-w-md items-start gap-3 rounded-2xl border px-4 py-3 text-left text-sm ${qc.warnings.length ? "border-amber-500/40 bg-amber-500/8" : "border-emerald-500/40 bg-emerald-500/8"}`}>
              {qc.warnings.length ? <TriangleAlert size={18} className="mt-0.5 flex-none text-amber-500" /> : <CheckCircle2 size={18} className="mt-0.5 flex-none text-emerald-500" />}
              <div>
                <b>{qc.warnings.length ? "Yuborilmadi — iltimos, qayta yozing:" : "Yuborildi — rahmat!"}</b>
                {qc.warnings.map((w) => <div key={w}>• {w}</div>)}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {msg && <p className="mt-4 max-w-md text-sm text-rose-500">{msg}</p>}
      </div>
      <p className="px-5 pb-5 text-center text-xs text-faint">Tinch xonada, mikrofondan bir xil masofada yozing. Yozuvlar faqat OMZU loyihasi uchun ishlatiladi.</p>
    </div>
  );
}

function Center({ children }: { children: React.ReactNode }) {
  return <div className="flex min-h-dvh flex-col items-center justify-center px-6 py-10 text-center">{children}</div>;
}
