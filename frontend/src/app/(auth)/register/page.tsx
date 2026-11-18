"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox, Field, Input } from "@/components/ui/input";
import { ErrorNotice } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

function Register() {
  const { t } = useT();
  const router = useRouter();
  const p = useSearchParams();
  const { refresh } = useAuth();
  const [f, setF] = useState({ email: "", password: "", display_name: "", accept_terms: false });
  const { run, busy, error } = useAction();
  const cfg = useApi<any>("/config/public");
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => {
      await api("/auth/register", { body: { ...f, display_name: f.display_name || null, referral_code: p.get("ref"), invite_code: p.get("invite") } });
      await refresh();
      router.replace("/app/onboarding");
    }); }}>
      <div><h1 className="text-2xl font-bold">{t("auth.register.title")}</h1><p className="text-sm text-muted-foreground">{t("auth.register.sub")}</p></div>
      <Field label={t("auth.email")} htmlFor="r-email"><Input id="r-email" type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
      <Field label={t("auth.password")} htmlFor="r-pw" hint={t("auth.register.pwHint")}>
        <Input id="r-pw" type="password" required minLength={10} autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
      </Field>
      <Field label={t("auth.register.name")} htmlFor="r-name"><Input id="r-name" autoComplete="nickname" value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></Field>
      <Checkbox checked={f.accept_terms} onChange={(e) => setF({ ...f, accept_terms: e.target.checked })} required
        label={<>{t("auth.register.terms")} (<Link href="/rechtliches/nutzungsbedingungen" className="text-primary underline" target="_blank">Nutzung</Link>, <Link href="/rechtliches/datenschutz" className="text-primary underline" target="_blank">Datenschutz</Link>)</>} />
      <ErrorNotice error={error} />
      <Button className="w-full" disabled={busy}>{t("auth.register.button")}</Button>
      {(cfg.data?.auth?.google || cfg.data?.auth?.apple) && <div className="space-y-2">
        {cfg.data?.auth?.google && <a href="/api/auth/oauth/google/start" className={buttonVariants({ variant: "outline", className: "w-full" })}>{t("auth.login.google")}</a>}
        {cfg.data?.auth?.apple && <a href="/api/auth/oauth/apple/start" className={buttonVariants({ variant: "outline", className: "w-full" })}>{t("auth.login.apple")}</a>}
      </div>}
      <p className="text-center text-sm">{t("auth.register.hasAccount")} <Link href="/login" className="text-primary">{t("auth.login.title")}</Link></p>
    </form>
  );
}

export default function Page() { return <Suspense><Register /></Suspense>; }
