import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, Mic, Paperclip, Square } from "lucide-react";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { ACCEPT } from "../types";

export type ComposerHandle = { focus: () => void };

export const Composer = forwardRef<ComposerHandle, {
  streaming: boolean; onSend: (text: string) => void; onStop: () => void; onFiles: (files: File[]) => void;
}>(function Composer({ streaming, onSend, onStop, onFiles }, ref) {
  const [value, setValue] = useState("");
  const ta = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  useImperativeHandle(ref, () => ({ focus: () => ta.current?.focus() }));

  useEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 220) + "px";
  }, [value]);

  const submit = () => {
    if (streaming) return onStop();
    const t = value.trim();
    if (!t) return;
    onSend(t);
    setValue("");
  };
  const canSend = streaming || value.trim().length > 0;

  return (
    <div className="flex-none px-5 pb-4 max-sm:px-3 max-sm:pb-3">
      <motion.form
        layout
        onSubmit={(e) => { e.preventDefault(); submit(); }}
        className="relative mx-auto flex max-w-3xl items-end gap-2 rounded-3xl border border-line bg-surface py-2.5 pl-5 pr-2.5 shadow-soft transition-[border-color,box-shadow] duration-300 focus-within:border-accent/50 focus-within:shadow-[0_0_0_4px_rgba(109,93,252,.12)]"
      >
        <textarea
          ref={ta}
          rows={1}
          value={value}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); }
          }}
          placeholder="OMZU'ga yozing…"
          className="max-h-[220px] min-h-[26px] flex-1 resize-none bg-transparent py-1.5 leading-relaxed outline-none placeholder:text-faint"
        />
        <input ref={fileInput} type="file" multiple accept={ACCEPT} className="hidden"
          onChange={(e) => { const fs = Array.from(e.target.files ?? []); if (fs.length) onFiles(fs); e.target.value = ""; }} />
        <motion.button type="button" whileTap={{ scale: 0.88 }} onClick={() => fileInput.current?.click()}
          title="Fayl qoʻshish (PDF, Word, Markdown, kod…) — bilim bazasiga"
          className="grid h-9 w-9 place-items-center rounded-xl text-muted transition-colors hover:bg-surface-2 hover:text-fg">
          <Paperclip size={18} />
        </motion.button>
        <button type="button" disabled title="Ovozli kiritish — tez orada"
          className="grid h-9 w-9 place-items-center rounded-xl text-faint opacity-60">
          <Mic size={18} />
        </button>
        <motion.button
          type="submit"
          disabled={!canSend}
          whileHover={canSend ? { scale: 1.07, rotate: streaming ? 0 : -5 } : undefined}
          whileTap={canSend ? { scale: 0.9 } : undefined}
          title={streaming ? "Toʻxtatish" : "Yuborish"}
          className={`grid h-[38px] w-[38px] flex-none place-items-center rounded-[13px] text-white transition-[opacity,filter] ${
            streaming ? "bg-fg text-bg" : "bg-grad"} ${canSend ? "" : "opacity-35 grayscale"}`}
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={streaming ? "stop" : "send"}
              initial={{ scale: 0.4, opacity: 0, rotate: -90 }}
              animate={{ scale: 1, opacity: 1, rotate: 0 }}
              exit={{ scale: 0.4, opacity: 0, rotate: 90 }}
              transition={{ duration: 0.18 }}
            >
              {streaming ? <Square size={14} fill="currentColor" /> : <ArrowUp size={19} strokeWidth={2.4} />}
            </motion.span>
          </AnimatePresence>
        </motion.button>
      </motion.form>
      <div className="mx-auto mt-2 max-w-3xl text-center text-xs text-faint">
        OMZU xato qilishi mumkin. Muhim maʼlumotlarni tekshiring.
      </div>
    </div>
  );
});
