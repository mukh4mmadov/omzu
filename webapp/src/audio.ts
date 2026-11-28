
export function encodeWav(chunks: Float32Array[], sr: number): Blob {
  const len = chunks.reduce((a, c) => a + c.length, 0);
  const buf = new ArrayBuffer(44 + len * 2);
  const v = new DataView(buf);
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + len * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, len * 2, true);
  let o = 44;
  for (const c of chunks) for (let i = 0; i < c.length; i++, o += 2) {
    const s = Math.max(-1, Math.min(1, c[i]));
    v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

export type QC = { duration: number; peak: number; rms_db: number; snr_db: number; warnings: string[] };

export function quickQC(chunks: Float32Array[], sr: number): QC {
  const n = chunks.reduce((a, c) => a + c.length, 0);
  const x = new Float32Array(n);
  let o = 0;
  for (const c of chunks) { x.set(c, o); o += c.length; }
  const a = Math.exp((-2 * Math.PI * 60) / sr);
  let py = 0, px = 0, peak = 0;
  for (let i = 0; i < n; i++) {
    const y = a * (py + x[i] - px);
    px = x[i]; py = y; x[i] = y;
    peak = Math.max(peak, Math.abs(y));
  }
  const frame = Math.floor(sr * 0.03);
  const e: number[] = [];
  for (let i = 0; i + frame <= n; i += frame) {
    let s = 0;
    for (let j = i; j < i + frame; j++) s += x[j] * x[j];
    e.push(Math.sqrt(s / frame) + 1e-9);
  }
  const sorted = [...e].sort((p, q) => p - q);
  const pct = (p: number) => sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p))] ?? 1e-9;
  const rms_db = 20 * Math.log10(pct(0.9));
  const snr_db = rms_db - 20 * Math.log10(pct(0.1));
  const duration = n / sr;
  const warnings: string[] = [];
  if (duration < 1.5) warnings.push("juda qisqa — gapni toʻliq oʻqidingizmi?");
  if (peak >= 0.99) warnings.push("ovoz juda baland (xirillash bor) — mikrofonni biroz uzoqlashtiring");
  if (rms_db < -38) warnings.push("ovoz juda past — mikrofonga yaqinroq gapiring");
  if (snr_db < 25) warnings.push("fon shovqini sezilarli — tinchroq joyda yozing");
  return { duration: +duration.toFixed(2), peak: +peak.toFixed(3), rms_db: +rms_db.toFixed(1), snr_db: +snr_db.toFixed(1), warnings };
}

export type Mic = { ctx: AudioContext; stop: () => void; buf: Float32Array[]; samples: () => number; level: () => number[] };

export async function openMic(bars = 32): Promise<Mic> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
  });
  const ctx = new AudioContext();
  const src = ctx.createMediaStreamSource(stream);
  const an = ctx.createAnalyser(); an.fftSize = 256;
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const buf: Float32Array[] = [];
  let total = 0, live = true;
  proc.onaudioprocess = (e) => {
    if (!live) return;
    const d = new Float32Array(e.inputBuffer.getChannelData(0));
    buf.push(d); total += d.length;
  };
  src.connect(an); src.connect(proc); proc.connect(ctx.destination);
  const data = new Uint8Array(an.frequencyBinCount);
  return {
    ctx, buf,
    samples: () => total,
    level: () => { an.getByteFrequencyData(data); return Array.from({ length: bars }, (_, i) => data[Math.floor((i / bars) * data.length * 0.7)] / 255); },
    stop: () => {
      live = false;
      proc.onaudioprocess = null;
      proc.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      ctx.close();
    },
  };
}
