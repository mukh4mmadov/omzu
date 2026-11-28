import { AnimatePresence, motion } from "motion/react";
import { ArrowDown, FileUp, PanelLeftOpen } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamChat } from "./api";
import { Composer, type ComposerHandle } from "./components/Composer";
import { TaskManager } from "./components/Tasks";
import { Recorder } from "./components/Recorder";
import { MessageView } from "./components/MessageView";
import { ListItem, Modal, Toasts, type Toast } from "./components/Overlays";
import { Sidebar } from "./components/Sidebar";
import { Welcome } from "./components/Welcome";
import { useMediaQuery, useTheme } from "./hooks";
import type { Conversation, DocInfo, Memory, Message, Reminder, Status } from "./types";

const USER_NAME = "Ozodbek";

function chime() {
  try {
    const ac = new AudioContext();
    [660, 880, 990].forEach((f, i) => {
      const o = ac.createOscillator(), g = ac.createGain(), t = ac.currentTime + i * 0.18;
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.18, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
      o.connect(g).connect(ac.destination);
      o.start(t); o.stop(t + 0.55);
    });
  } catch {  }
}

export default function App() {
  const { pref, cycle } = useTheme();
  const mobile = useMediaQuery("(max-width: 820px)");
  const [sideOpen, setSideOpen] = useState(!mobile);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [cid, setCid] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [modal, setModal] = useState<null | "mem" | "rem" | "docs" | "tasks">(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [docs, setDocs] = useState<DocInfo[]>([]);
  const [dragging, setDragging] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const dragDepth = useRef(0);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [atBottom, setAtBottom] = useState(true);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<ComposerHandle>(null);
  const stick = useRef(true);

  useEffect(() => setSideOpen(!mobile), [mobile]);

  const toast = useCallback((icon: string, title: string, text: string, ms = 4200) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, icon, title, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ms);
  }, []);

  const loadConvs = useCallback(() => api.conversations().then(setConvs).catch(() => {}), []);
  useEffect(() => {
    loadConvs();
    api.status().then(setStatus).catch(() => setStatus({ name: "OMZU", mode: "tools", label: "Server bilan aloqa yoʻq" }));
  }, [loadConvs]);

  useEffect(() => {
    const poll = () => api.dueReminders().then((due) => due.forEach((r) => {
      toast("⏰", "Eslatma", `${r.text} — ${r.due}`, 15000);
      chime();
      if ("Notification" in window && Notification.permission === "granted") new Notification("OMZU — eslatma", { body: r.text });
    })).catch(() => {});
    poll();
    const t = setInterval(poll, 20000);
    const ask = () => { if ("Notification" in window && Notification.permission === "default") Notification.requestPermission(); };
    document.addEventListener("click", ask, { once: true });
    return () => clearInterval(t);
  }, [toast]);

  const toBottom = useCallback((smooth = false) => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }, []);
  useEffect(() => { if (stick.current) toBottom(); }, [msgs, toBottom]);
  const onScroll = () => {
    const el = scroller.current!;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    stick.current = near;
    setAtBottom(near);
  };

  const newChat = useCallback(() => {
    abort.current?.abort();
    setCid(null); setMsgs([]);
    if (mobile) setSideOpen(false);
    setTimeout(() => composer.current?.focus(), 50);
  }, [mobile]);

  const openConv = async (id: string) => {
    if (streaming) return;
    setCid(id);
    const m = await api.conversation(id);
    stick.current = true;
    setMsgs(m);
    if (mobile) setSideOpen(false);
  };

  const deleteConv = async (id: string) => {
    await api.deleteConversation(id);
    if (id === cid) newChat();
    loadConvs();
  };

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); newChat(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") { e.preventDefault(); setSideOpen((s) => !s); }
      if (e.key === "Escape") setModal(null);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [newChat]);

  const send = async (text: string) => {
    if (streaming) return;
    const localId = "local-" + Date.now();
    stick.current = true;
    setMsgs((m) => [...m,
      { id: "u-" + localId, role: "user", content: text },
      { id: localId, role: "assistant", content: "", streaming: true, extra: { tools: [], sources: [] } }]);
    setStreaming(true);
    const ctrl = new AbortController();
    abort.current = ctrl;
    let botId = localId;
    const patch = (f: (m: Message) => Message) =>
      setMsgs((all) => all.map((m) => (m.id === botId ? f(m) : m)));
    try {
      await streamChat(text, cid, (ev) => {
        if (ev.type === "meta") {
          const old = botId;
          botId = ev.message_id;
          setMsgs((all) => all.map((m) => (m.id === old ? { ...m, id: ev.message_id } : m)));
          if (ev.conversation_id !== cid) { setCid(ev.conversation_id); loadConvs(); }
        } else if (ev.type === "status") {
          patch((m) => ({ ...m, status: ev.text }));
        } else if (ev.type === "tool") {
          patch((m) => ({ ...m, extra: { tools: [...(m.extra?.tools ?? []), ev], sources: m.extra?.sources ?? [] } }));
        } else if (ev.type === "sources") {
          patch((m) => ({ ...m, extra: { tools: m.extra?.tools ?? [], sources: ev.items } }));
        } else if (ev.type === "token") {
          patch((m) => ({ ...m, content: m.content + ev.text }));
        }
      }, ctrl.signal);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        patch((m) => ({ ...m, content: m.content + "\n\n⚠️ Server bilan aloqa uzildi. `OMZU.bat` ishlayotganini tekshiring." }));
      }
    }
    patch((m) => ({ ...m, streaming: false, status: null }));
    setStreaming(false);
    abort.current = null;
    loadConvs();
  };

  const showDocs = async () => { setDocs(await api.documents()); setModal("docs"); };

  const uploadFiles = async (files: File[]) => {
    toast("📎", "Yuklanmoqda…", files.map((f) => f.name).join(", "), 2500);
    try {
      const res = await api.uploadDocuments(files);
      for (const r of res) {
        if (r.ok) toast("📚", "Bilim bazasiga qoʻshildi", `${r.name} — ${r.chunks} boʻlak. Endi undan savol bering.`, 6000);
        else toast("⚠️", `${r.name}: qoʻshilmadi`, r.error ?? "", 7000);
      }
      if (modal === "docs") setDocs(await api.documents());
    } catch {
      toast("⚠️", "Yuklab boʻlmadi", "Server bilan aloqa yoʻq", 6000);
    }
  };

  useEffect(() => {
    const has = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => { if (has(e)) { e.preventDefault(); dragDepth.current++; setDragging(true); } };
    const over = (e: DragEvent) => { if (has(e)) e.preventDefault(); };
    const leave = (e: DragEvent) => { if (has(e) && --dragDepth.current <= 0) { dragDepth.current = 0; setDragging(false); } };
    const drop = (e: DragEvent) => {
      if (!has(e)) return;
      e.preventDefault(); dragDepth.current = 0; setDragging(false);
      const fs = Array.from(e.dataTransfer?.files ?? []);
      if (fs.length) uploadFiles(fs);
    };
    window.addEventListener("dragenter", enter); window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave); window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter); window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave); window.removeEventListener("drop", drop);
    };
  });

  const showMemories = async () => { setMemories(await api.memories()); setModal("mem"); };
  const showReminders = async () => { setReminders(await api.reminders()); setModal("rem"); };
  const title = convs.find((c) => c.id === cid)?.title ?? "";

  return (
    <div className="flex h-dvh">
      <AnimatePresence initial={false}>
        {sideOpen && (
          mobile ? (
            <>
              <motion.div key="scrim" className="fixed inset-0 z-30 bg-black/35"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setSideOpen(false)} />
              <motion.aside key="side-m" className="fixed inset-y-0 left-0 z-40 shadow-float"
                initial={{ x: -290 }} animate={{ x: 0 }} exit={{ x: -290 }} transition={{ type: "spring", stiffness: 380, damping: 36 }}>
                <Sidebar convs={convs} current={cid} status={status} theme={pref} onNew={newChat} onOpen={openConv}
                  onDelete={deleteConv} onClose={() => setSideOpen(false)} onTheme={cycle} onMemories={showMemories} onReminders={showReminders} onDocs={showDocs} onTasks={() => setModal("tasks")} onVoice={() => { setVoiceOpen(true); if (mobile) setSideOpen(false); }} />
              </motion.aside>
            </>
          ) : (
            <motion.aside key="side-d" className="flex-none overflow-hidden"
              initial={{ width: 0, opacity: 0 }} animate={{ width: 272, opacity: 1 }} exit={{ width: 0, opacity: 0 }}
              transition={{ type: "spring", stiffness: 320, damping: 34 }}>
              <Sidebar convs={convs} current={cid} status={status} theme={pref} onNew={newChat} onOpen={openConv}
                onDelete={deleteConv} onClose={() => setSideOpen(false)} onTheme={cycle} onMemories={showMemories} onReminders={showReminders} onDocs={showDocs} onTasks={() => setModal("tasks")} onVoice={() => { setVoiceOpen(true); if (mobile) setSideOpen(false); }} />
            </motion.aside>
          )
        )}
      </AnimatePresence>

      <main className="relative flex min-w-0 flex-1 flex-col">
        <div className="flex h-[54px] flex-none items-center gap-2 px-3.5">
          <AnimatePresence>
            {!sideOpen && (
              <motion.button initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }}
                onClick={() => setSideOpen(true)} title="Yon panel (Ctrl+B)"
                className="grid h-[34px] w-[34px] place-items-center rounded-[10px] text-muted transition hover:bg-surface-2 hover:text-fg">
                <PanelLeftOpen size={18} />
              </motion.button>
            )}
          </AnimatePresence>
          <motion.div key={title} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="truncate text-sm text-muted">{title}</motion.div>
        </div>

        <div ref={scroller} onScroll={onScroll} className="flex-1 overflow-y-auto">
          {msgs.length === 0 ? (
            <Welcome name={USER_NAME} onPick={send} />
          ) : (
            <div className="mx-auto max-w-3xl px-5 pb-10 pt-2 max-sm:px-4">
              {msgs.map((m) => <MessageView key={m.id} m={m} toast={toast} />)}
            </div>
          )}
        </div>

        <AnimatePresence>
          {!atBottom && msgs.length > 0 && (
            <motion.button
              initial={{ opacity: 0, y: 10, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.9 }}
              onClick={() => toBottom(true)}
              className="absolute bottom-[112px] left-1/2 z-10 grid h-9 w-9 -translate-x-1/2 place-items-center rounded-full border border-line bg-surface text-muted shadow-float transition hover:text-fg"
            >
              <ArrowDown size={17} />
            </motion.button>
          )}
        </AnimatePresence>

        <Composer ref={composer} streaming={streaming} onSend={send} onStop={() => abort.current?.abort()} onFiles={uploadFiles} />
      </main>

      <Modal open={modal === "mem"} onClose={() => setModal(null)} title="🧠 Xotira"
        sub="OMZU siz haqingizda eslab qolgan narsalar. Ular modelning ichida emas, faqat shu kompyuterda saqlanadi.">
        {memories.length === 0 && <div className="py-6 text-center text-faint">Hozircha boʻsh. «Eslab qol: …» deb yozing.</div>}
        <AnimatePresence>
          {memories.map((m, i) => (
            <ListItem key={m.id} i={i} text={m.fact} sub={m.created}
              onDelete={async () => { await api.forget(m.id); setMemories(await api.memories()); }} />
          ))}
        </AnimatePresence>
      </Modal>
      <Modal open={modal === "rem"} onClose={() => setModal(null)} title="⏰ Eslatmalar"
        sub="Vaqti kelganda shu sahifada xabar va ovozli signal chiqadi (sahifa ochiq turishi kerak).">
        {reminders.length === 0 && <div className="py-6 text-center text-faint">Faol eslatmalar yoʻq.</div>}
        {reminders.map((r, i) => <ListItem key={r.id} i={i} text={r.text} sub={r.due} />)}
      </Modal>
      <Modal open={modal === "tasks"} onClose={() => setModal(null)} title="✅ Vazifalar"
        sub="Bajarish kerak boʻlgan ishlar. Chatda ham boshqarish mumkin: «vazifa qoʻsh: …», «vazifalarim», «2-vazifa bajarildi».">
        <TaskManager />
      </Modal>
      <Modal open={modal === "docs"} onClose={() => setModal(null)} title="📚 Hujjatlar"
        sub="Siz qoʻshgan fayllar bilim bazasida turadi — OMZU savolga javob berishdan oldin ularni oʻqiydi. 📎 tugmasi yoki faylni oynaga sudrab tashlash orqali qoʻshing.">
        {docs.length === 0 && <div className="py-6 text-center text-faint">Hali hujjat qoʻshilmagan.</div>}
        <AnimatePresence>
          {docs.map((d, i) => (
            <ListItem key={d.name} i={i} text={d.name} sub={`${d.chunks} boʻlak · ${(d.chars / 1000).toFixed(1)} ming belgi`}
              onDelete={async () => { await api.deleteDocument(d.name); setDocs(await api.documents()); }} />
          ))}
        </AnimatePresence>
      </Modal>
      <AnimatePresence>
        {dragging && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="pointer-events-none fixed inset-0 z-[70] grid place-items-center bg-bg/70 backdrop-blur-md"
          >
            <motion.div
              initial={{ scale: 0.9, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 300, damping: 22 }}
              className="flex flex-col items-center gap-3 rounded-3xl border-2 border-dashed border-accent/60 bg-surface px-14 py-10 text-center shadow-float"
            >
              <div className="bg-grad animate-float grid h-16 w-16 place-items-center rounded-2xl text-white"><FileUp size={30} /></div>
              <div className="text-lg font-semibold">Faylni shu yerga tashlang</div>
              <div className="text-sm text-muted">PDF, Word, Markdown, TXT, HTML yoki kod — bilim bazasiga qoʻshiladi</div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      <Recorder open={voiceOpen} onClose={() => setVoiceOpen(false)} />
      <Toasts items={toasts} />
    </div>
  );
}
