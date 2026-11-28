export function Orb({ size = 34, busy = false, glow = false }: { size?: number; busy?: boolean; glow?: boolean }) {
  return (
    <div className={`orb ${busy ? "busy" : ""}`} style={{ width: size, height: size }} aria-hidden>
      {glow && <div className="orb-glow" />}
    </div>
  );
}
