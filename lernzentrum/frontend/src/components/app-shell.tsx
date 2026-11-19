"use client";
// Authenticated shell: side navigation in landscape/desktop, bottom tab bar in portrait/iPhone.
import { BookOpen, CalendarDays, GraduationCap, Home, Inbox, Layers, Mic, Moon, Settings, Sun, Type } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";
import { cn, Spinner } from "./ui";
import { useApp } from "./providers";

const NAV = [
  { href: "/", label: t().nav.home, icon: Home },
  { href: "/live", label: t().nav.live, icon: Mic },
  { href: "/modules", label: t().nav.modules, icon: Layers },
  { href: "/learn", label: t().nav.learn, icon: GraduationCap },
  { href: "/library", label: t().nav.library, icon: BookOpen },
  { href: "/inbox", label: t().nav.inbox, icon: Inbox },
  { href: "/calendar", label: t().nav.calendar, icon: CalendarDays },
  { href: "/settings", label: t().nav.settings, icon: Settings },
];
const MOBILE = ["/", "/live", "/modules", "/learn", "/inbox"];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, reloadUser, theme, setTheme, largeType, setLargeType } = useApp();
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [reviewCount, setReviewCount] = useState(0);

  useEffect(() => {
    reloadUser().then((u) => {
      if (!u) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      else if (!u.setup_done) router.replace("/setup");
      else setReady(true);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!ready) return;
    api.get<{ items: unknown[]; events: unknown[] }>("/review").then((r) => setReviewCount(r.items.length + r.events.length)).catch(() => undefined);
  }, [ready, pathname]);

  if (!ready || !user) return <Spinner label="Lernzentrum startet …" />;
  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const live = pathname.startsWith("/live/");

  return (
    <div className="flex min-h-dvh">
      <aside className="safe-top sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-border bg-surface px-3 py-4 lg:flex">
        <Link href="/" className="mb-6 flex items-center gap-2 px-2">
          <img src="/logo.svg" alt="" className="h-9 w-9" />
          <span className="text-lg font-bold tracking-tight">Lernzentrum</span>
        </Link>
        <nav className="flex flex-1 flex-col gap-1" aria-label="Hauptnavigation">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex h-11 items-center gap-3 rounded-xl px-3 font-medium transition-colors",
                active(href) ? "bg-primary text-primary-fg" : "text-text hover:bg-surface-2",
              )}
            >
              <Icon className="h-5 w-5" aria-hidden />
              {label}
              {href === "/inbox" && reviewCount > 0 && (
                <span className="ml-auto rounded-full bg-pruefen px-2 text-xs font-semibold text-white">{reviewCount}</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="flex gap-1 border-t border-border pt-3">
          <button
            className="flex h-11 flex-1 items-center justify-center rounded-xl hover:bg-surface-2"
            onClick={() => setTheme(theme === "dark" ? "light" : theme === "light" ? "system" : "dark")}
            aria-label={`Farbschema: ${theme === "system" ? "System" : theme === "dark" ? "Dunkel" : "Hell"}`}
            title={`Farbschema: ${theme === "system" ? "System" : theme === "dark" ? "Dunkel" : "Hell"}`}
          >
            {theme === "dark" ? <Moon className="h-5 w-5" /> : theme === "light" ? <Sun className="h-5 w-5" /> : <span className="text-xs font-semibold">Auto</span>}
          </button>
          <button
            className={cn("flex h-11 flex-1 items-center justify-center rounded-xl hover:bg-surface-2", largeType && "bg-surface-2")}
            onClick={() => setLargeType(!largeType)}
            aria-pressed={largeType}
            aria-label="Große Schrift"
            title="Große Schrift"
          >
            <Type className="h-5 w-5" />
          </button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        {user.is_demo && !live && (
          <div className="safe-top bg-primary/10 px-4 py-1.5 text-center text-xs text-text">
            Demo-Modus mit Beispieldaten · Keine echten Keys nötig
          </div>
        )}
        <main className={cn("mx-auto w-full flex-1 px-4 pb-28 pt-4 lg:px-8 lg:pb-10", live ? "max-w-none" : "max-w-6xl")}>{children}</main>
      </div>
      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-surface/95 backdrop-blur lg:hidden" aria-label="Navigation">
        {NAV.filter((n) => MOBILE.includes(n.href)).map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className={cn("relative flex h-16 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium", active(href) ? "text-primary" : "text-muted")}>
            <Icon className="h-6 w-6" aria-hidden />
            {label}
            {href === "/inbox" && reviewCount > 0 && <span className="absolute right-[28%] top-2 h-2.5 w-2.5 rounded-full bg-pruefen" />}
          </Link>
        ))}
        <Link href="/settings" className={cn("flex h-16 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium", active("/settings") ? "text-primary" : "text-muted")}>
          <Settings className="h-6 w-6" aria-hidden />
          Mehr
        </Link>
      </nav>
    </div>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight lg:text-[1.75rem]">{title}</h1>
        {subtitle && <p className="mt-0.5 text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
