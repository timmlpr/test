"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity, Archive, Bell, BookLock, Briefcase, CreditCard, FileSearch, FileText, Fingerprint, Gauge, Globe, Home, Image as ImageIcon,
  KeyRound, LogOut, Mail, Menu, MessageCircle, Network, Radar, Settings, Shield, ShieldAlert, Share2, Timer, User as UserIcon, Users, X,
} from "lucide-react";
import { LogoMark } from "./logo";
import { ThemeToggle } from "./theme-toggle";
import { useAuth } from "./providers";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { brand } from "@/lib/brand";
import { useApi } from "@/lib/hooks";
import { CookieBanner, FeedbackButton } from "./site";

type Item = { href: string; key: string; icon: React.ComponentType<{ className?: string }>; premium?: boolean };
const GROUPS: { key: string; items: Item[] }[] = [
  { key: "overview", items: [{ href: "/app", key: "home", icon: Home }, { href: "/app/risk", key: "risk", icon: Gauge }, { href: "/app/timeline", key: "timeline", icon: Timer }] },
  { key: "reduce", items: [{ href: "/app/scan", key: "scan", icon: Radar }, { href: "/app/results", key: "results", icon: FileSearch },
    { href: "/app/breaches", key: "breaches", icon: ShieldAlert }, { href: "/app/requests", key: "requests", icon: Mail }, { href: "/app/reports", key: "reports", icon: FileText }] },
  { key: "check", items: [{ href: "/app/scam", key: "scam", icon: Shield }, { href: "/app/domain", key: "domain", icon: Globe },
    { href: "/app/image", key: "image", icon: ImageIcon }, { href: "/app/passwords", key: "passwords", icon: KeyRound }] },
  { key: "protect", items: [{ href: "/app/checklist", key: "checklist", icon: Fingerprint }, { href: "/app/social", key: "social", icon: Share2 },
    { href: "/app/monitor", key: "monitor", icon: Activity, premium: true }] },
  { key: "organize", items: [{ href: "/app/subscriptions", key: "subscriptions", icon: Briefcase, premium: true }, { href: "/app/documents", key: "documents", icon: Archive, premium: true },
    { href: "/app/estate", key: "estate", icon: BookLock, premium: true }, { href: "/app/graph", key: "graph", icon: Network, premium: true },
    { href: "/app/assistant", key: "assistant", icon: MessageCircle, premium: true }] },
  { key: "account", items: [{ href: "/app/profile", key: "profile", icon: UserIcon }, { href: "/app/billing", key: "billing", icon: CreditCard },
    { href: "/app/family", key: "family", icon: Users }, { href: "/app/settings", key: "settings", icon: Settings }] },
];
const MOBILE = ["/app", "/app/scan", "/app/requests", "/app/assistant"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const { t } = useT();
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const notif = useApi<{ unread: number }>(user ? "/notifications" : null);
  useEffect(() => { if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(path)}`); }, [loading, user, router, path]);
  useEffect(() => { setOpen(false); }, [path]);
  if (!user) return <div className="flex min-h-screen items-center justify-center text-muted-foreground">{t("common.loading")}</div>;
  const active = (href: string) => (href === "/app" ? path === "/app" : path.startsWith(href));
  const items = GROUPS.flatMap((g) => g.items);

  const nav = (
    <nav aria-label="Hauptnavigation" className="space-y-5">
      {GROUPS.map((g) => (
        <div key={g.key}>
          <p className="mb-1 px-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t(`nav.groups.${g.key}`)}</p>
          <ul className="space-y-0.5">
            {g.items.map((it) => (
              <li key={it.href}>
                <Link href={it.href} aria-current={active(it.href) ? "page" : undefined}
                  className={cn("flex items-center gap-3 rounded-md px-3 py-2 text-sm", active(it.href) ? "bg-primary/10 font-medium text-primary" : "hover:bg-muted")}>
                  <it.icon className="h-4 w-4" />
                  <span className="flex-1">{t(`nav.${it.key}`)}</span>
                  {it.premium && user.tier !== "premium" && <span className="text-[10px] font-semibold text-primary">PRO</span>}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {user.role === "admin" && (
        <Link href="/admin" className="flex items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-muted"><Shield className="h-4 w-4" />{t("nav.admin")}</Link>
      )}
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-card focus:p-2">Zum Inhalt springen</a>
      <aside className="hidden border-r bg-card lg:block">
        <div className="sticky top-0 flex h-screen flex-col gap-6 overflow-y-auto p-4">
          <Link href="/app" className="flex items-center gap-2 px-2 font-semibold"><LogoMark /> {brand.name}</Link>
          {nav}
          <button onClick={logout} className="mt-auto flex items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-muted"><LogOut className="h-4 w-4" />{t("nav.logout")}</button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-col pb-20 lg:pb-0">
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b bg-background/90 px-4 py-2 backdrop-blur">
          <button className="rounded-md p-2 hover:bg-muted lg:hidden" onClick={() => setOpen(true)} aria-label="Menü öffnen"><Menu className="h-5 w-5" /></button>
          <Link href="/app" className="flex items-center gap-2 font-semibold lg:hidden"><LogoMark className="h-7 w-7" /> {brand.name}</Link>
          <div className="ml-auto flex items-center gap-1">
            {user.is_demo && <span className="mr-2 rounded-full bg-warn/15 px-2 py-0.5 text-xs font-medium text-warn">{t("common.demo")}</span>}
            <Link href="/app/notifications" className="relative rounded-md p-2 hover:bg-muted" aria-label={t("notif.title")}>
              <Bell className="h-5 w-5" />
              {!!notif.data?.unread && <span className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full bg-bad" aria-label={`${notif.data.unread} ungelesen`} />}
            </Link>
            <ThemeToggle />
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6">{children}</main>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menü">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-[min(85vw,320px)] overflow-y-auto bg-card p-4 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <span className="flex items-center gap-2 font-semibold"><LogoMark className="h-7 w-7" />{brand.name}</span>
              <button onClick={() => setOpen(false)} className="rounded p-2 hover:bg-muted" aria-label="Menü schließen"><X className="h-5 w-5" /></button>
            </div>
            {nav}
            <button onClick={logout} className="mt-6 flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-muted"><LogOut className="h-4 w-4" />{t("nav.logout")}</button>
          </div>
        </div>
      )}
      <nav aria-label="Schnellnavigation" className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t bg-card lg:hidden">
        {MOBILE.map((href) => {
          const it = items.find((i) => i.href === href)!;
          return (
            <Link key={href} href={href} className={cn("flex flex-col items-center gap-0.5 py-2 text-[11px]", active(href) ? "text-primary" : "text-muted-foreground")}>
              <it.icon className="h-5 w-5" />{t(`nav.${it.key}`)}
            </Link>
          );
        })}
        <button onClick={() => setOpen(true)} className="flex flex-col items-center gap-0.5 py-2 text-[11px] text-muted-foreground"><Menu className="h-5 w-5" />{t("nav.more")}</button>
      </nav>
      <FeedbackButton />
      <CookieBanner />
    </div>
  );
}
