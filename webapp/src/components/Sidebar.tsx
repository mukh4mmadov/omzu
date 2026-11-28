import { AnimatePresence, motion } from "motion/react";
import { Bell, Brain, FileText, ListTodo, Mic, Monitor, Moon, PanelLeftClose, Plus, Sun, Trash2 } from "lucide-react";
import type { ThemePref } from "../hooks";
import type { Conversation, Status } from "../types";
import { Orb } from "./Orb";

function groupOf(iso: string) {
  const d = new Date(iso), now = new Date();
  const days = Math.floor((new Date(now.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 864e5);
  return days === 0 ? "Bugun" : days === 1 ? "Kecha" : days < 7 ? "Shu hafta" : "Avvalroq";
}

const THEME = {
  system: { icon: Monitor, label: "Tizim mavzusi" },
  dark: { icon: Moon, label: "Tungi rejim" },
  light: { icon: Sun, label: "Kunduzgi rejim" },
};

export function Sidebar(props: {
  convs: Conversation[]; current: string | null; status: Status | null; theme: ThemePref;
  onNew: () => void; onOpen: (id: string) => void; onDelete: (id: string) => void;
  onClose: () => void; onTheme: () => void; onMemories: () => void; onReminders: () => void; onDocs: () => void;
  onTasks: () => void; onVoice: () => void;
}) {
  const { convs, current, status } = props;
  const ThemeIcon = THEME[props.theme].icon;
  let last = "";
  return (
    <div className="flex h-full w-[272px] flex-col border-r border-line bg-sidebar">
      <div className="flex items-center gap-2.5 px-4 pb-2.5 pt-[18px]">
        <Orb size={34} />
        <div className="flex-1 leading-tight">
          <div className="text-[15px] font-bold tracking-[.16em]">OMZU</div>
          <div className="text-[11px] text-faint">Ozodbek Muhammadov</div>
        </div>
        <button onClick={props.onClose} title="Yon panelni yopish (Ctrl+B)"
          className="grid h-[34px] w-[34px] place-items-center rounded-[10px] text-muted transition hover:bg-surface-2 hover:text-fg">
          <PanelLeftClose size={18} />
        </button>
      </div>

      <motion.button
        whileHover={{ y: -1 }} whileTap={{ scale: 0.98 }}
        onClick={props.onNew}
        className="mx-3 mb-1.5 mt-2 flex items-center gap-2.5 rounded-xl border border-line bg-surface px-3 py-2.5 font-medium shadow-soft transition-colors hover:border-line-strong"
      >
        <span className="bg-grad grid h-[22px] w-[22px] place-items-center rounded-[7px] text-white"><Plus size={15} strokeWidth={2.6} /></span>
        Yangi suhbat
        <span className="ml-auto text-[11px] text-faint">Ctrl+K</span>
      </motion.button>

      <div className="flex-1 overflow-y-auto px-2 pb-3 pt-1.5">
        {convs.length === 0 && <div className="px-2.5 pt-4 text-xs text-faint">Suhbatlar shu yerda koʻrinadi</div>}
        <AnimatePresence initial={false}>
          {convs.map((c) => {
            const g = groupOf(c.updated);
            const header = g !== last ? g : null;
            last = g;
            return (
              <motion.div key={c.id} layout initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20, height: 0 }} transition={{ type: "spring", stiffness: 400, damping: 34 }}>
                {header && <div className="px-2.5 pb-1.5 pt-3.5 text-[11px] font-semibold uppercase tracking-wider text-faint">{header}</div>}
                <div
                  onClick={() => props.onOpen(c.id)}
                  className={`group relative flex cursor-pointer items-center gap-1.5 rounded-[10px] px-2.5 py-2 text-sm transition-colors ${
                    c.id === current ? "text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"}`}
                >
                  {c.id === current && (
                    <motion.div layoutId="active-conv" className="absolute inset-0 rounded-[10px] bg-surface shadow-soft"
                      transition={{ type: "spring", stiffness: 500, damping: 38 }} />
                  )}
                  <span className="relative flex-1 truncate">{c.title || "Suhbat"}</span>
                  <button
                    title="Oʻchirish"
                    onClick={(e) => { e.stopPropagation(); props.onDelete(c.id); }}
                    className="relative grid h-6 w-6 place-items-center rounded-md text-faint opacity-0 transition hover:bg-rose-500/15 hover:text-rose-500 group-hover:opacity-100"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      <div className="grid gap-0.5 border-t border-line p-2.5">
        {[
          { icon: ListTodo, label: "Vazifalar", on: props.onTasks },
          { icon: Mic, label: "Ovoz yozish", on: props.onVoice },
          { icon: FileText, label: "Hujjatlar", on: props.onDocs },
          { icon: Brain, label: "Xotira", on: props.onMemories },
          { icon: Bell, label: "Eslatmalar", on: props.onReminders },
          { icon: ThemeIcon, label: THEME[props.theme].label, on: props.onTheme },
        ].map(({ icon: I, label, on }) => (
          <button key={label} onClick={on}
            className="flex items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-sm text-muted transition hover:bg-surface-2 hover:text-fg">
            <I size={17} /> {label}
          </button>
        ))}
        <div className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-faint">
          <span className="relative flex h-2 w-2">
            <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${status?.mode === "model" ? "bg-emerald-500" : "bg-amber-500"}`} />
            <span className={`relative inline-flex h-2 w-2 rounded-full ${status?.mode === "model" ? "bg-emerald-500" : "bg-amber-500"}`} />
          </span>
          <span className="leading-snug">{status?.label ?? "Ulanmoqda…"}</span>
        </div>
      </div>
    </div>
  );
}
