import { AnimatePresence, motion } from "motion/react";
import { Copy, Link2, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type Invite = { id: string; speaker_name: string; consent_at: string | null; active: boolean; uploads: number; seconds: number; pending: number };

export function RemotePanel({ onSynced }: { onSynced: () => void }) {
  const [open, setOpen] = useState(false);
  const [configured, setConfigured] = useState(true);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [note, setNote] = useState("");
  const [link, setLink] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const j = await (await fetch("/api/voice/invites")).json();
      setConfigured(j.configured); setInvites(j.invites);
    } catch {  }
  }, []);

  const sync = useCallback(async () => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch("/api/voice/sync", { method: "POST" });
      const j = await r.json();
      if (!r.ok) setMsg(j.detail ?? "Xatolik");
      else {
        setMsg(j.new ? `Yangi: ${j.new} · hisoblandi: ${j.saved} · hisoblanmadi: ${j.rejected}` : "Yangi yozuv yoʻq");
        if (j.new) onSynced();
      }
    } catch { setMsg("Internet yoʻq"); }
    setBusy(false); load();
  }, [load, onSynced]);

  useEffect(() => { if (open) { load(); sync(); } }, [open]);

  const create = async () => {
    setBusy(true);
    const r = await fetch("/api/voice/invites", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }) });
    const j = await r.json();
    setBusy(false);
    if (!r.ok) { setMsg(j.detail ?? "Xatolik"); return; }
    setLink(j.link); setNote(""); load();
  };
  const off = async (id: string) => { await fetch(`/api/voice/invites/${id}`, { method: "DELETE" }); load(); };

  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-1.5 text-sm transition hover:border-line-strong">
        <Link2 size={15} /> Masofadan
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6 }}
            className="absolute left-0 top-11 z-10 w-[360px] rounded-2xl border border-line bg-surface p-3 shadow-float">
            {!configured ? <p className="text-sm text-muted">Supabase sozlanmagan (.env).</p> : (<>
              <div className="mb-2 text-sm font-medium">Do‘st uchun havola</div>
              <div className="flex gap-2">
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Izoh (ixtiyoriy)"
                  className="min-w-0 flex-1 rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-sm outline-none focus:border-accent" />
                <button disabled={busy} onClick={create} className="bg-grad rounded-lg px-3 py-1 text-sm font-medium text-white disabled:opacity-40">Yaratish</button>
              </div>
              {link && (
                <div className="mt-2 flex items-center gap-2 rounded-lg bg-surface-2 p-2 text-xs">
                  <span className="min-w-0 flex-1 break-all">{link}</span>
                  <button onClick={() => navigator.clipboard.writeText(link)} className="text-accent" title="Nusxalash"><Copy size={15} /></button>
                </div>
              )}
              <div className="mb-1 mt-3 flex items-center justify-between text-sm font-medium">
                Havolalar
                <button disabled={busy} onClick={sync} className="flex items-center gap-1 text-xs text-accent disabled:opacity-40">
                  <RefreshCw size={13} className={busy ? "animate-spin" : ""} /> Yozuvlarni olish
                </button>
              </div>
              {msg && <div className="mb-1 text-xs text-muted">{msg}</div>}
              <div className="max-h-48 overflow-y-auto">
                {invites.length === 0 && <div className="text-xs text-muted">Hali havola yoʻq</div>}
                {invites.map((i) => (
                  <div key={i.id} className="flex items-center gap-2 rounded-lg px-1.5 py-1.5 text-xs">
                    <span className="flex-1">
                      <span className="block text-sm">{i.speaker_name || "Kutilmoqda…"}{!i.active && " (oʻchirilgan)"}</span>
                      <span className="text-muted">{i.consent_at ? "rozilik bor" : "hali ochilmagan"} · {Math.round(i.seconds / 60)} daq · {i.uploads} yozuv</span>
                    </span>
                    {i.active && <button onClick={() => off(i.id)} className="text-muted hover:text-red-500" title="Havolani oʻchirish"><Trash2 size={15} /></button>}
                  </div>
                ))}
              </div>
            </>)}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
