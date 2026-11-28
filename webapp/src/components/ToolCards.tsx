import { motion } from "motion/react";
import { BellRing, Droplets, TrendingDown, TrendingUp, Wind } from "lucide-react";
import type { ToolEvent } from "../types";
import { TasksCard } from "./Tasks";

const SKY_ICON: [string, string][] = [
  ["momaqaldiroq", "⛈️"], ["qor", "❄️"], ["jala", "🌧️"], ["yomg", "🌧️"], ["tuman", "🌫️"],
  ["qisman", "⛅"], ["bulutli", "☁️"], ["ochiq", "☀️"],
];
const skyIcon = (s: string) => SKY_ICON.find(([k]) => s.includes(k))?.[1] ?? "🌤️";
const WEEKDAYS = ["Ya", "Du", "Se", "Ch", "Pa", "Ju", "Sh"];
const fmt = (n: number) => Number(n).toLocaleString("ru-RU", { maximumFractionDigits: 2 }).replace(",", ".");

const cardMotion = {
  initial: { opacity: 0, y: 14, scale: 0.97 },
  animate: { opacity: 1, y: 0, scale: 1 },
  transition: { type: "spring" as const, stiffness: 260, damping: 24 },
};

function Weather({ r }: { r: any }) {
  const n = r.now;
  const sky: string = n.sky;
  const tone = /yomg|jala|momaq/.test(sky)
    ? "from-slate-600 via-slate-700 to-blue-900"
    : n.temp_c >= 24 ? "from-amber-500 via-orange-500 to-pink-500"
    : n.temp_c <= 5 ? "from-sky-500 via-blue-500 to-indigo-500"
    : "from-blue-500 via-indigo-500 to-violet-500";
  return (
    <motion.div {...cardMotion} className={`relative mb-3 overflow-hidden rounded-2xl bg-gradient-to-br ${tone} p-5 text-white shadow-float`}>
      <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10 blur-2xl" />
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold opacity-95">{r.city}{r.country ? `, ${r.country}` : ""}</div>
          <motion.div
            className="text-[52px] font-light leading-none tracking-tight"
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
          >
            {Math.round(n.temp_c)}°
          </motion.div>
          <div className="mt-1 text-sm opacity-90">{sky}</div>
        </div>
        <div className="animate-float text-6xl drop-shadow-lg">{skyIcon(sky)}</div>
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-[12.5px] opacity-90">
        <span>His qilinishi {Math.round(n.feels_like_c)}°</span>
        <span className="flex items-center gap-1"><Droplets size={13} /> {n.humidity}%</span>
        <span className="flex items-center gap-1"><Wind size={13} /> {Math.round(n.wind_kmh)} km/soat</span>
      </div>
      {r.forecast.length > 1 && (
        <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
          {r.forecast.map((d: any, i: number) => (
            <motion.div
              key={d.date}
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 + i * 0.05 }}
              className="min-w-[74px] flex-none rounded-xl bg-white/15 px-2 py-2 text-center text-xs backdrop-blur-sm"
            >
              <div className="opacity-90">{WEEKDAYS[new Date(d.date + "T12:00").getDay()]}</div>
              <div className="my-0.5 text-xl">{skyIcon(d.sky)}</div>
              <div className="text-[15px] font-semibold">{Math.round(d.max_c)}°</div>
              <div className="opacity-75">{Math.round(d.min_c)}°</div>
            </motion.div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

function Currency({ r }: { r: any }) {
  const ch = r.change || 0;
  const big = r.amount !== 1 ? r.total_uzs : r.rate_uzs;
  return (
    <motion.div {...cardMotion} className="mb-3 rounded-2xl border border-line bg-surface p-5 shadow-soft">
      <div className="text-[13px] text-muted">{r.name || r.currency} · Markaziy bank · {r.date}</div>
      <div className="mt-1 flex flex-wrap items-baseline gap-3">
        <span className="text-grad text-[32px] font-semibold tracking-tight">{fmt(big)} soʻm</span>
        <span className="text-[13px] text-muted">{r.amount !== 1 ? `${fmt(r.amount)} ${r.currency}` : `1 ${r.currency}`}</span>
        {ch !== 0 && (
          <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${ch > 0 ? "bg-emerald-500/10 text-emerald-500" : "bg-rose-500/10 text-rose-500"}`}>
            {ch > 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />} {fmt(Math.abs(ch))}
          </span>
        )}
      </div>
    </motion.div>
  );
}

function ReminderCard({ r }: { r: any }) {
  return (
    <motion.div {...cardMotion} className="mb-3 flex items-center gap-3 rounded-2xl border border-line bg-surface p-4 shadow-soft">
      <div className="bg-grad animate-ring grid h-11 w-11 place-items-center rounded-xl text-white"><BellRing size={20} /></div>
      <div>
        <div className="font-semibold">{r.text}</div>
        <div className="text-[13px] text-muted">{r.due}</div>
      </div>
    </motion.div>
  );
}

const SRC_COLOR: Record<string, string> = {
  "Kun.uz": "bg-sky-500/12 text-sky-600 dark:text-sky-400",
  "Gazeta.uz": "bg-rose-500/12 text-rose-600 dark:text-rose-400",
  "Spot.uz": "bg-amber-500/14 text-amber-600 dark:text-amber-400",
  "UzA": "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400",
  "Daryo.uz": "bg-violet-500/12 text-violet-600 dark:text-violet-400",
};

function News({ r }: { r: any }) {
  return (
    <motion.div {...cardMotion} className="mb-3 overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
      {r.items.map((n: any, i: number) => (
        <motion.a
          key={n.link} href={n.link} target="_blank" rel="noopener noreferrer"
          initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.08 + i * 0.05 }}
          className="group/n flex items-start gap-3 border-b border-line px-4 py-3 transition-colors last:border-0 hover:bg-surface-2"
        >
          <span className={`mt-0.5 flex-none rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${SRC_COLOR[n.source] ?? "bg-surface-2 text-muted"}`}>
            {n.source}
          </span>
          <span className="min-w-0 flex-1 text-[14px] leading-snug group-hover/n:text-accent">{n.title}</span>
          <span className="flex-none pt-0.5 text-[11.5px] text-faint">{n.time.split(",")[0]}</span>
        </motion.a>
      ))}
    </motion.div>
  );
}

export function ToolCard({ ev }: { ev: ToolEvent }) {
  const r = ev.result;
  if (!r || r.error) return null;
  if (ev.name === "weather") return <Weather r={r} />;
  if (ev.name === "currency") return <Currency r={r} />;
  if (ev.name === "add_reminder") return <ReminderCard r={r} />;
  if (ev.name === "list_tasks" && r.tasks?.length) return <TasksCard initial={r.tasks} />;
  if (ev.name === "news" && r.items?.length) return <News r={r} />;
  return null;
}
