"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { KeyRound } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { getPasskey, passkeysSupported } from "@/lib/webauthn";

function Login() {
  const { t } = useT();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/app";
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"pw" | "2fa">(params.get("step") === "2fa" ? "2fa" : "pw");
  const { run, busy, error } = useAction();
  const cfg = useApi<any>("/config/public");
  const [pkOk, setPkOk] = useState(false);
  useEffect(() => { setPkOk(passkeysSupported()); }, []);
  const done = async () => { await refresh(); router.replace(next.startsWith("/") ? next : "/app"); };

  if (step === "2fa") return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/auth/totp/verify", { body: { code } }); await done(); }); }}>
      <h1 className="text-2xl font-bold">{t("auth.2fa.title")}</h1>
      <p className="text-sm text-muted-foreground">{t("auth.2fa.sub")}</p>
      <Input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" autoFocus aria-label={t("auth.2fa.title")} />
      <ErrorNotice error={error} />
      <Button className="w-full" disabled={busy}>{t("auth.login.button")}</Button>
    </form>
  );

  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-bold">{t("auth.login.title")}</h1><p className="text-sm text-muted-foreground">{t("auth.login.sub")}</p></div>
      {cfg.data?.demo_mode && (
        <Alert><strong>{t("auth.demo.title")}:</strong> {t("auth.demo.text")}<br />
          <button className="mt-1 font-mono text-xs underline" onClick={() => { setEmail("demo@demo.example.com"); setPw("FadeprintDemo1!"); }}>demo@demo.example.com / FadeprintDemo1!</button>
        </Alert>
      )}
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => {
        const r = await api<any>("/auth/login", { body: { email, password: pw } });
        if (r.requires_2fa) setStep("2fa"); else await done();
      }); }}>
        <Field label={t("auth.email")} htmlFor="email"><Input id="email" type="email" required autoComplete="username webauthn" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label={t("auth.password")} htmlFor="pw"><Input id="pw" type="password" required autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
        <ErrorNotice error={error} />
        <Button className="w-full" disabled={busy}>{t("auth.login.button")}</Button>
      </form>
      <div className="space-y-2">
        {pkOk && <Button variant="outline" className="w-full" onClick={() => run(async () => {
          const b = await api<any>("/auth/passkey/login/begin", { method: "POST" });
          const credential = await getPasskey(b.options);
          await api("/auth/passkey/login/finish", { body: { handle: b.handle, credential } });
          await done();
        })}><KeyRound className="h-4 w-4" />{t("auth.login.passkey")}</Button>}
        {cfg.data?.auth?.google && <a href="/api/auth/oauth/google/start" className={buttonVariants({ variant: "outline", className: "w-full" })}>{t("auth.login.google")}</a>}
        {cfg.data?.auth?.apple && <a href="/api/auth/oauth/apple/start" className={buttonVariants({ variant: "outline", className: "w-full" })}>{t("auth.login.apple")}</a>}
      </div>
      <div className="flex justify-between text-sm">
        <Link href="/forgot" className="text-primary">{t("auth.login.forgot")}</Link>
        <span>{t("auth.login.noAccount")} <Link href="/register" className="text-primary">{t("auth.register.title")}</Link></span>
      </div>
    </div>
  );
}

export default function Page() { return <Suspense><Login /></Suspense>; }
