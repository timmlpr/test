"use client";
// App-wide state: current user, theme (light/dark/system), large type, dimming, toasts.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

type Theme = "system" | "light" | "dark";

interface Ctx {
  user: User | null;
  setUser: (u: User | null) => void;
  reloadUser: () => Promise<User | null>;
  theme: Theme;
  setTheme: (t: Theme) => void;
  largeType: boolean;
  setLargeType: (v: boolean) => void;
  dim: boolean;
  setDim: (v: boolean) => void;
  toast: (msg: string, tone?: "ok" | "error" | "info") => void;
}

const AppCtx = createContext<Ctx | null>(null);

export function useApp() {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside provider");
  return c;
}

function applyTheme(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#12151a" : "#f7f6f2");
}

function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode */
  }
}

export function Providers({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [theme, setThemeState] = useState<Theme>("system");
  const [largeType, setLargeTypeState] = useState(false);
  const [dim, setDimState] = useState(false);
  const [toasts, setToasts] = useState<{ id: number; msg: string; tone: string }[]>([]);

  useEffect(() => {
    try {
      setThemeState((localStorage.getItem("lz-theme") as Theme) || "system");
      setLargeTypeState(localStorage.getItem("lz-large") === "1");
      setDimState(localStorage.getItem("lz-dim") === "1");
    } catch {
      /* ignore */
    }
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    applyTheme(theme);
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const fn = () => applyTheme("system");
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, [theme]);

  useEffect(() => {
    document.documentElement.classList.toggle("large-type", largeType);
  }, [largeType]);

  useEffect(() => {
    document.body.classList.toggle("dim", dim);
  }, [dim]);

  const setTheme = (t: Theme) => {
    setThemeState(t);
    store("lz-theme", t);
  };
  const setLargeType = (v: boolean) => {
    setLargeTypeState(v);
    store("lz-large", v ? "1" : "0");
  };
  const setDim = (v: boolean) => {
    setDimState(v);
    store("lz-dim", v ? "1" : "0");
  };
  const reloadUser = useCallback(async () => {
    try {
      const u = await api.get<User>("/auth/me");
      setUser(u);
      return u;
    } catch {
      setUser(null);
      return null;
    }
  }, []);
  const toast = useCallback((msg: string, tone: "ok" | "error" | "info" = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  return (
    <AppCtx.Provider value={{ user, setUser, reloadUser, theme, setTheme, largeType, setLargeType, dim, setDim, toast }}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-24 z-[60] flex flex-col items-center gap-2 px-4 lg:bottom-6" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto max-w-md rounded-xl px-4 py-2.5 text-sm font-medium shadow-lg"
            style={{
              background: t.tone === "error" ? "var(--unsicher)" : t.tone === "ok" ? "var(--sicher)" : "var(--text)",
              color: t.tone === "info" ? "var(--bg)" : "#fff",
            }}
          >
            {t.msg}
          </div>
        ))}
      </div>
    </AppCtx.Provider>
  );
}
