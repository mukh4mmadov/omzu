import { AnimatePresence, motion } from "motion/react";
import { Check, Copy, ThumbsDown, ThumbsUp } from "lucide-react";
import { memo, useState } from "react";
import { api } from "../api";
import type { Message } from "../types";
import { Markdown } from "./Markdown";
import { Orb } from "./Orb";
import { ToolCard } from "./ToolCards";

const enter = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition: { type: "spring" as const, stiffness: 300, damping: 30 },
};

function IconBtn({ title, onClick, active, danger, children }: {
  title: string; onClick: () => void; active?: boolean; danger?: boolean; children: React.ReactNode;
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.88 }}
      title={title}
      onClick={onClick}
      className={`grid h-8 w-8 place-items-center rounded-lg transition-colors hover:bg-surface-2 ${
        active ? (danger ? "text-rose-500" : "text-accent") : "text-faint hover:text-fg"}`}
    >
      {children}
    </motion.button>
  );
}

function Actions({ m, toast }: { m: Message; toast: (icon: string, title: string, text: string) => void }) {
  const [rating, setRating] = useState<number | null>(m.rating ?? null);
  const [copied, setCopied] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const [correction, setCorrection] = useState("");
  return (
    <>
      <div className="mt-2 flex gap-0.5 opacity-0 transition-opacity duration-300 group-hover:opacity-100 [@media(hover:none)]:opacity-100">
        <IconBtn title="Nusxa olish" onClick={async () => {
          try { await navigator.clipboard.writeText(m.content); } catch {  }
          setCopied(true); setTimeout(() => setCopied(false), 1400);
        }}>
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </IconBtn>
        <IconBtn title="Yaxshi javob" active={rating === 1} onClick={() => {
          setRating(1); setCorrecting(false); api.feedback(m.id, 1);
          toast("👍", "Rahmat!", "Bu javob yaxshi namuna sifatida saqlandi.");
        }}>
          <ThumbsUp size={16} />
        </IconBtn>
        <IconBtn title="Yomon javob" danger active={rating === -1} onClick={() => {
          setRating(-1); setCorrecting(true); api.feedback(m.id, -1);
        }}>
          <ThumbsDown size={16} />
        </IconBtn>
      </div>
      <AnimatePresence>
        {correcting && (
          <motion.div
            initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-2 grid gap-2 pb-1">
              <textarea
                autoFocus
                value={correction}
                onChange={(e) => setCorrection(e.target.value)}
                placeholder="Toʻgʻri javob qanday boʻlishi kerak edi? (ixtiyoriy — OMZU shundan oʻrganadi)"
                className="min-h-[76px] w-full resize-y rounded-xl border border-line bg-surface px-3 py-2.5 outline-none transition focus:border-accent"
              />
              <div className="flex justify-end gap-2">
                <button className="rounded-lg border border-line px-3.5 py-1.5 text-sm transition hover:bg-surface-2"
                  onClick={() => setCorrecting(false)}>Bekor qilish</button>
                <button className="bg-grad rounded-lg px-3.5 py-1.5 text-sm font-medium text-white transition active:scale-95"
                  onClick={() => {
                    api.feedback(m.id, -1, correction.trim() || null);
                    setCorrecting(false);
                    toast("📝", "Saqlandi", "Tuzatish keyingi oʻqitishda ishlatiladi.");
                  }}>Saqlash</button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

export const MessageView = memo(function MessageView({ m, toast }: {
  m: Message; toast: (icon: string, title: string, text: string) => void;
}) {
  if (m.role === "user") {
    return (
      <motion.div {...enter} className="my-6 flex justify-end">
        <div className="max-w-[82%] whitespace-pre-wrap break-words rounded-[20px] rounded-br-md bg-bubble px-4 py-2.5">
          {m.content}
        </div>
      </motion.div>
    );
  }
  const tools = m.extra?.tools ?? [];
  const sources = m.extra?.sources ?? [];
  const thinking = m.streaming && !m.content;
  return (
    <motion.div {...enter} className="group my-6 grid grid-cols-[34px_1fr] gap-3.5 max-sm:grid-cols-[28px_1fr] max-sm:gap-2.5">
      <div className="pt-0.5"><Orb size={30} busy={m.streaming} /></div>
      <div className="min-w-0">
        <AnimatePresence>
          {thinking && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }}
              className="shimmer mb-1.5 text-sm"
            >
              {m.status || "Oʻylanmoqda…"}
            </motion.div>
          )}
        </AnimatePresence>
        {tools.map((t, i) => <ToolCard key={i} ev={t} />)}
        {sources.length > 0 && (
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {sources.map((s, i) => (
              <motion.span
                key={s.title + i}
                initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.06 }}
                className="flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs text-muted"
              >
                <i className="bg-grad h-1.5 w-1.5 rounded-full" />{s.title}
              </motion.span>
            ))}
          </div>
        )}
        <div className={m.streaming && m.content ? "caret" : ""}>
          <Markdown text={m.content} />
        </div>
        {!m.streaming && m.content && <Actions m={m} toast={toast} />}
      </div>
    </motion.div>
  );
});
