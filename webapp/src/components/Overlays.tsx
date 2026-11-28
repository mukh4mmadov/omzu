import { AnimatePresence, motion } from "motion/react";
import { Trash2, X } from "lucide-react";
import type { ReactNode } from "react";

export function Modal({ open, onClose, title, sub, children }: {
  open: boolean; onClose: () => void; title: string; sub: string; children: ReactNode;
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          onClick={(e) => e.target === e.currentTarget && onClose()}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.94, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }} transition={{ type: "spring", stiffness: 380, damping: 30 }}
            className="max-h-[80vh] w-full max-w-[520px] overflow-auto rounded-[22px] border border-line bg-surface p-6 shadow-float"
          >
            <div className="mb-1 flex items-center justify-between">
              <h3 className="text-lg font-semibold">{title}</h3>
              <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-faint transition hover:bg-surface-2 hover:text-fg"><X size={18} /></button>
            </div>
            <div className="mb-4 text-[13.5px] text-muted">{sub}</div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function ListItem({ text, sub, onDelete, i }: { text: string; sub: string; onDelete?: () => void; i: number }) {
  return (
    <motion.div
      layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 30 }}
      transition={{ delay: i * 0.04 }}
      className="mb-2 flex items-center gap-2.5 rounded-xl border border-line px-3.5 py-2.5"
    >
      <span className="flex-1">{text}<br /><small className="text-faint">{sub}</small></span>
      {onDelete && (
        <button onClick={onDelete} title="Oʻchirish"
          className="grid h-8 w-8 place-items-center rounded-lg text-faint transition hover:bg-rose-500/15 hover:text-rose-500"><Trash2 size={16} /></button>
      )}
    </motion.div>
  );
}

export type Toast = { id: number; icon: string; title: string; text: string };

export function Toasts({ items }: { items: Toast[] }) {
  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[60] grid gap-2.5">
      <AnimatePresence>
        {items.map((t) => (
          <motion.div
            key={t.id} layout
            initial={{ opacity: 0, x: 40, scale: 0.95 }} animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 40 }} transition={{ type: "spring", stiffness: 360, damping: 28 }}
            className="pointer-events-auto flex min-w-[260px] max-w-[360px] items-center gap-3 rounded-2xl border border-line bg-surface px-4 py-3 shadow-float"
          >
            <div className="animate-ring text-[22px]">{t.icon}</div>
            <div><b className="text-sm">{t.title}</b><small className="block text-[13px] text-muted">{t.text}</small></div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
