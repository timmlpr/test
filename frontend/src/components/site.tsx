"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { MessageSquarePlus } from "lucide-react";
import { Logo } from "./logo";
import { ThemeToggle } from "./theme-toggle";
import { Button, buttonVariants } from "./ui/button";
import { Dialog } from "./ui/misc";
import { Textarea } from "./ui/input";
import { useAuth } from "./providers";
import { useT } from "@/lib/i18n";
import { api } from "@/lib/api";
import { brand } from "@/lib/brand";
import { usePathname } from "next/navigation";

export function SiteHeader() {
  const { t } = useT();
  const { user } = useAuth();
  return (
    <header className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur">
      <div className="container flex h-16 items-center gap-4">
        <Link href="/" aria-label={`${brand.name} Startseite`}><Logo /></Link>
        <nav className="ml-6 hidden gap-5 text-sm md:flex" aria-label="Seiten">
          <Link href="/#funktionen" className="hover:text-primary">Funktionen</Link>
          <Link href="/preise" className="hover:text-primary">Preise</Link>
          <Link href="/blog" className="hover:text-primary">{t("footer.blog")}</Link>
          <Link href="/#faq" className="hover:text-primary">FAQ</Link>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          {user ? (
            <Link href="/app" className={buttonVariants({ size: "sm" })}>Zur App</Link>
          ) : (
            <>
              <Link href="/login" className={buttonVariants({ variant: "ghost", size: "sm" })}>{t("auth.login.title")}</Link>
              <Link href="/register" className={buttonVariants({ size: "sm", className: "hidden sm:inline-flex" })}>{t("landing.hero.cta")}</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  const { t } = useT();
  const links = [
    ["/rechtliches/impressum", "footer.imprint"], ["/rechtliches/datenschutz", "footer.privacy"], ["/rechtliches/agb", "footer.terms"],
    ["/rechtliches/widerruf", "footer.withdrawal"], ["/rechtliches/nutzungsbedingungen", "footer.usage"], ["/rechtliches/keine-rechtsberatung", "footer.noLegal"],
    ["/kuendigen", "footer.cancel"], ["/missbrauch-melden", "footer.abuse"], ["/blog", "footer.blog"],
  ];
  return (
    <footer className="mt-16 border-t bg-card">
      <div className="container grid gap-8 py-10 md:grid-cols-[1fr_2fr]">
        <div className="space-y-2">
          <Logo />
          <p className="text-sm text-muted-foreground">{brand.tagline_de}</p>
          <p className="text-xs text-muted-foreground">Gehostet in Deutschland (EU).</p>
        </div>
        <ul className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
          {links.map(([href, k]) => <li key={href}><Link href={href} className="hover:text-primary">{t(k)}</Link></li>)}
          <li><button className="hover:text-primary" onClick={() => { try { localStorage.removeItem("fp_cookie"); } catch {} location.reload(); }}>{t("footer.cookies")}</button></li>
        </ul>
      </div>
    </footer>
  );
}

/** Only technically necessary cookies exist. The banner informs; any future tracking stays off until opt-in. */
export function CookieBanner() {
  const { t } = useT();
  const [show, setShow] = useState(false);
  useEffect(() => { try { setShow(!localStorage.getItem("fp_cookie")); } catch { setShow(false); } }, []);
  if (!show) return null;
  const choose = (v: string) => { try { localStorage.setItem("fp_cookie", v); } catch {} setShow(false); };
  return (
    <div role="region" aria-label="Cookie-Hinweis" className="fixed inset-x-2 bottom-20 z-50 mx-auto max-w-xl rounded-lg border bg-card p-4 shadow-lg lg:bottom-4">
      <p className="text-sm">{t("cookie.text")} <Link href="/rechtliches/datenschutz" className="text-primary underline">{t("footer.privacy")}</Link></p>
      <div className="mt-3 flex gap-2">
        <Button size="sm" onClick={() => choose("necessary")}>{t("cookie.ok")}</Button>
        <Button size="sm" variant="outline" onClick={() => choose("necessary")}>{t("cookie.decline")}</Button>
      </div>
    </div>
  );
}

export function FeedbackButton() {
  const { t } = useT();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [done, setDone] = useState(false);
  return (
    <>
      <button onClick={() => { setOpen(true); setDone(false); }} className="fixed bottom-20 right-3 z-30 hidden rounded-full border bg-card p-3 shadow-md hover:bg-muted lg:bottom-4 lg:block"
        aria-label={t("feedback.title")} title={t("feedback.title")}>
        <MessageSquarePlus className="h-5 w-5" />
      </button>
      <Dialog open={open} onClose={() => setOpen(false)} title={t("feedback.title")}>
        {done ? <p>{t("feedback.thanks")}</p> : (
          <form className="space-y-3" onSubmit={async (e) => { e.preventDefault(); await api("/feedback", { body: { message: msg, page: path } }); setDone(true); setMsg(""); }}>
            <Textarea value={msg} onChange={(e) => setMsg(e.target.value)} placeholder={t("feedback.placeholder")} required minLength={3} aria-label={t("feedback.title")} />
            <Button type="submit">{t("feedback.send")}</Button>
          </form>
        )}
      </Dialog>
    </>
  );
}
