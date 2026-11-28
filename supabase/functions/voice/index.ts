import { createClient } from "npm:@supabase/supabase-js@2.49.1";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type, authorization, apikey, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const CONSENT_TEXT =
  "Men ushbu ovoz yozuvlarimni OMZU sunʼiy intellekt modelini oʻqitish va OMZU mahsulotida ovoz sifatida ishlatish uchun ixtiyoriy ravishda beraman.";
const MAX_UPLOADS_PER_DAY = 1500;

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
  auth: { persistSession: false },
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });

async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "faqat POST" }, 405);
  try {
    const body = await req.json();
    const token = String(body.token ?? "");
    if (token.length < 24) return json({ error: "Havola notoʻgʻri" }, 401);
    const { data: inv } = await db.from("voice_invites").select("*")
      .eq("token_hash", await sha256(token)).eq("active", true).maybeSingle();
    if (!inv) return json({ error: "Havola yaroqsiz yoki oʻchirilgan" }, 401);

    if (body.action === "session") {
      const { data: ups } = await db.from("voice_uploads").select("item_id, duration").eq("invite_id", inv.id);
      return json({
        name: inv.speaker_name, consent: Boolean(inv.consent_at), consent_text: CONSENT_TEXT,
        done: [...new Set((ups ?? []).map((u) => u.item_id))],
        seconds: (ups ?? []).reduce((a, u) => a + (u.duration ?? 0), 0),
      });
    }

    if (body.action === "consent") {
      const name = String(body.name ?? "").trim().slice(0, 80);
      if (!name || body.agree !== true) return json({ error: "Ism va rozilik kerak" }, 400);
      await db.from("voice_invites").update({
        speaker_name: name, consent_text: CONSENT_TEXT, consent_at: new Date().toISOString(),
      }).eq("id", inv.id);
      return json({ ok: true });
    }

    if (!inv.consent_at) return json({ error: "Avval rozilik bering" }, 403);
    const itemId = String(body.item_id ?? "");
    if (!/^[sp]\d{4}$/.test(itemId)) return json({ error: "notoʻgʻri matn raqami" }, 400);

    if (body.action === "upload_url") {
      const since = new Date(Date.now() - 864e5).toISOString();
      const { count } = await db.from("voice_uploads").select("id", { count: "exact", head: true })
        .eq("invite_id", inv.id).gte("created_at", since);
      if ((count ?? 0) >= MAX_UPLOADS_PER_DAY) return json({ error: "Bugungi limit tugadi" }, 429);
      const path = `${inv.speaker_id}/${itemId}_${Date.now()}.wav`;
      const { data, error } = await db.storage.from("voice").createSignedUploadUrl(path);
      if (error) return json({ error: error.message }, 500);
      return json({ path, signedUrl: data.signedUrl, uploadToken: data.token });
    }

    if (body.action === "commit") {
      const path = String(body.path ?? "");
      if (!path.startsWith(`${inv.speaker_id}/${itemId}_`)) return json({ error: "notoʻgʻri fayl yoʻli" }, 400);
      const marks = Array.isArray(body.marks) ? body.marks.slice(0, 20).map(Number) : null;
      const { error } = await db.from("voice_uploads").insert({
        invite_id: inv.id, speaker_id: inv.speaker_id, item_id: itemId, path, marks,
        duration: Number(body.duration) || null, client_qc: body.qc ?? null,
      });
      if (error) return json({ error: error.message }, 500);
      return json({ ok: true });
    }
    return json({ error: "nomaʼlum amal" }, 400);
  } catch (e) {
    return json({ error: String(e) }, 500);
  }
});
