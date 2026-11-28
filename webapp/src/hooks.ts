import { useCallback, useEffect, useState } from "react";

export type ThemePref = "system" | "light" | "dark";

const store = {
  get(k: string) {
    try { return localStorage.getItem(k); } catch { return null; }
  },
  set(k: string, v: string) {
    try { localStorage.setItem(k, v); } catch {  }
  },
};

export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(() => (store.get("omzu-theme") as ThemePref) || "system");
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = pref === "dark" || (pref === "system" && mq.matches);
      document.documentElement.dataset.theme = dark ? "dark" : "light";
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [pref]);
  const cycle = useCallback(() => {
    setPref((p) => {
      const next: ThemePref = p === "system" ? "dark" : p === "dark" ? "light" : "system";
      store.set("omzu-theme", next);
      return next;
    });
  }, []);
  return { pref, cycle };
}

export function useMediaQuery(q: string) {
  const [m, setM] = useState(() => matchMedia(q).matches);
  useEffect(() => {
    const mq = matchMedia(q);
    const on = () => setM(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [q]);
  return m;
}
