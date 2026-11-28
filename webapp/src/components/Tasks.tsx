import { AnimatePresence, motion } from "motion/react";
import { Check, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Task } from "../types";

function fmtDue(d: string | null) {
  if (!d) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const due = new Date(d + "T00:00");
  const days = Math.round((due.getTime() - today.getTime()) / 864e5);
  const label = days === 0 ? "bugun" : days === 1 ? "ertaga" : days === -1 ? "kecha" : d.split("-").reverse().join(".");
  return { label, overdue: days < 0 };
}

export function TaskRow({ t, onToggle, onDelete }: { t: Task; onToggle: () => void; onDelete?: () => void }) {
  const due = fmtDue(t.due);
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 30, height: 0 }}
      transition={{ type: "spring", stiffness: 420, damping: 34 }}
      className="group/task flex items-center gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-surface-2"
    >
      <motion.button
        whileTap={{ scale: 0.8 }}
        onClick={onToggle}
        className={`grid h-[22px] w-[22px] flex-none place-items-center rounded-full border-2 transition-colors ${
          t.done ? "border-transparent bg-grad text-white" : "border-line-strong hover:border-accent"}`}
      >
        <AnimatePresence>
          {t.done && (
            <motion.span initial={{ scale: 0, rotate: -45 }} animate={{ scale: 1, rotate: 0 }} exit={{ scale: 0 }}>
              <Check size={13} strokeWidth={3.2} />
            </motion.span>
          )}
        </AnimatePresence>
      </motion.button>
      <div className="min-w-0 flex-1">
        <div className={`relative w-fit max-w-full truncate transition-colors duration-300 ${t.done ? "text-faint" : ""}`}>
          {t.text}
          <motion.span
            className="absolute left-0 top-1/2 h-px bg-faint"
            initial={false} animate={{ width: t.done ? "100%" : "0%" }} transition={{ duration: 0.3, ease: "easeOut" }}
          />
        </div>
        {due && !t.done && (
          <div className={`text-xs ${due.overdue ? "text-rose-500" : "text-muted"}`}>{due.overdue ? "muddati oʻtgan · " : ""}{due.label}</div>
        )}
      </div>
      {onDelete && (
        <button onClick={onDelete} title="Oʻchirish"
          className="grid h-7 w-7 place-items-center rounded-lg text-faint opacity-0 transition hover:bg-rose-500/15 hover:text-rose-500 group-hover/task:opacity-100">
          <Trash2 size={14} />
        </button>
      )}
    </motion.div>
  );
}

export function TaskManager() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [text, setText] = useState("");
  const load = () => api.tasks().then(setTasks).catch(() => {});
  useEffect(() => { load(); }, []);
  const open = tasks.filter((t) => !t.done), done = tasks.filter((t) => t.done);
  return (
    <div>
      <form
        className="mb-3 flex gap-2"
        onSubmit={async (e) => { e.preventDefault(); if (!text.trim()) return; await api.addTask(text.trim()); setText(""); load(); }}
      >
        <input
          value={text} onChange={(e) => setText(e.target.value)} placeholder="Yangi vazifa…"
          className="flex-1 rounded-xl border border-line bg-surface px-3 py-2 outline-none transition focus:border-accent"
        />
        <motion.button whileTap={{ scale: 0.92 }} className="bg-grad grid h-10 w-10 place-items-center rounded-xl text-white"><Plus size={18} /></motion.button>
      </form>
      {tasks.length === 0 && <div className="py-6 text-center text-faint">Vazifalar yoʻq. Chatda ham yozish mumkin: «vazifa qoʻsh: …»</div>}
      <AnimatePresence initial={false}>
        {open.map((t) => (
          <TaskRow key={t.id} t={t} onToggle={async () => { await api.toggleTask(t.id, true); load(); }}
            onDelete={async () => { await api.deleteTask(t.id); load(); }} />
        ))}
      </AnimatePresence>
      {done.length > 0 && <div className="px-2 pb-1 pt-4 text-xs font-semibold uppercase tracking-wider text-faint">Bajarilgan · {done.length}</div>}
      <AnimatePresence initial={false}>
        {done.map((t) => (
          <TaskRow key={t.id} t={t} onToggle={async () => { await api.toggleTask(t.id, false); load(); }}
            onDelete={async () => { await api.deleteTask(t.id); load(); }} />
        ))}
      </AnimatePresence>
    </div>
  );
}

export function TasksCard({ initial }: { initial: Task[] }) {
  const [tasks, setTasks] = useState(initial);
  return (
    <motion.div
      initial={{ opacity: 0, y: 14, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 24 }}
      className="mb-3 rounded-2xl border border-line bg-surface p-2.5 shadow-soft"
    >
      {tasks.map((t) => (
        <TaskRow key={t.id} t={t} onToggle={async () => {
          await api.toggleTask(t.id, !t.done);
          setTasks((all) => all.map((x) => (x.id === t.id ? { ...x, done: !x.done } : x)));
        }} />
      ))}
    </motion.div>
  );
}
