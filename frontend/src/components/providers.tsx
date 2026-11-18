"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { I18nProvider, useT } from "@/lib/i18n";

// ---------------------------------------------------------------- theme (system default, choice persisted)
type Theme = "light" | "dark" | "system";
const ThemeCtx = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({ theme: "system", setTheme: () => {} });

export const themeInitScript = `(function(){try{var t=localStorage.getItem('fp_theme')||'system';var d=t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){}})();`;

function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("system");
  useEffect(() => { try { setThemeState((localStorage.getItem("fp_theme") as Theme) || "system"); } catch {} }, []);
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => document.documentElement.classList.toggle("dark", theme === "dark" || (theme === "system" && mq.matches));
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
  const setTheme = (t: Theme) => { setThemeState(t); try { localStorage.setItem("fp_theme", t); } catch {} };
  return <ThemeCtx.Provider value={{ theme, setTheme }}>{children}</ThemeCtx.Provider>;
}
export const useTheme = () => useContext(ThemeCtx);

// ---------------------------------------------------------------- session user
export type User = {
  id: string; email: string; display_name: string | null; email_verified: boolean; role: string; plan: string; tier: "free" | "premium";
  trial_ends_at: string | null; address_form: "du" | "sie"; locale: "de" | "en"; totp_enabled: boolean; is_demo: boolean; is_child: boolean; referral_code: string;
};
type AuthCtx = { user: User | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> };
const Auth = createContext<AuthCtx>({ user: null, loading: true, refresh: async () => {}, logout: async () => {} });

function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const { setForm } = useT();
  const refresh = useCallback(async () => {
    try {
      const r = await api<{ user: User }>("/auth/me");
      setUser(r.user);
      setForm(r.user.address_form);
    } catch { setUser(null); } finally { setLoading(false); }
  }, [setForm]);
  const logout = useCallback(async () => { await api("/auth/logout", { method: "POST" }); setUser(null); location.href = "/"; }, []);
  useEffect(() => { refresh(); }, [refresh]);
  return <Auth.Provider value={{ user, loading, refresh, logout }}>{children}</Auth.Provider>;
}
export const useAuth = () => useContext(Auth);

// ---------------------------------------------------------------- service worker (PWA)
function SW() {
  useEffect(() => {
    if ("serviceWorker" in navigator && location.hostname !== "127.0.0.1") navigator.serviceWorker.register("/sw.js").catch(() => {});
  }, []);
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AuthProvider>
          <SW />
          {children}
        </AuthProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}
