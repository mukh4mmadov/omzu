import { motion } from "motion/react";
import { Orb } from "./Orb";

const SUGGESTIONS = [
  { em: "🌤️", t: "Ob-havo", s: "Samarqandda ertaga ob-havo qanday?" },
  { em: "💵", t: "Valyuta kursi", s: "100 dollar necha soʻm?" },
  { em: "📰", t: "Yangiliklar", s: "Soʻnggi yangiliklar" },
  { em: "📚", t: "Bilim", s: "Mirzo Ulugʻbek kim?" },
];

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Xayrli tun" : h < 12 ? "Xayrli tong" : h < 18 ? "Xayrli kun" : "Xayrli kech";
}

const ease = [0.2, 0.8, 0.2, 1] as const;

export function Welcome({ name, onPick }: { name: string; onPick: (s: string) => void }) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center px-5 pb-6 pt-10 text-center">
      <motion.div
        initial={{ scale: 0.6, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 160, damping: 16 }}
      >
        <Orb size={96} glow />
      </motion.div>
      <motion.h1
        initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.1, ease }}
        className="title-sheen mb-1.5 mt-7 text-[clamp(26px,4vw,38px)] font-semibold tracking-tight"
      >
        {greeting()}, {name}
      </motion.h1>
      <motion.p
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.2, ease }}
        className="mb-8 text-muted"
      >
        Bugun sizga qanday yordam bera olaman?
      </motion.p>
      <div className="grid w-full max-w-[640px] grid-cols-2 gap-2.5 max-sm:grid-cols-1">
        {SUGGESTIONS.map((x, i) => (
          <motion.button
            key={x.t}
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 + i * 0.07, ease }}
            whileHover={{ y: -3 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => onPick(x.s)}
            className="rounded-2xl border border-line bg-surface px-4 py-3.5 text-left shadow-soft transition-[border-color,box-shadow] hover:border-accent/40 hover:shadow-float"
          >
            <b className="flex items-center gap-2 text-sm font-semibold"><span className="text-[17px]">{x.em}</span>{x.t}</b>
            <small className="text-[13px] text-muted">{x.s}</small>
          </motion.button>
        ))}
      </div>
    </div>
  );
}
