"use client";
import Link from "next/link";
import { useState } from "react";
import { Check } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Alert } from "@/components/ui/misc";
import { Identifiers } from "@/components/app/identifiers";
import { ErrorNotice } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export default function Onboarding() {
  const { t } = useT();
  const { user, refresh } = useAuth();
  const home = useApi<any>("/home");
  const [result, setResult] = useState<any>(null);
  const { run, busy, error } = useAction();
  const o = home.data?.onboarding;
  const step = !o || o.identifiers === 0 ? 1 : o.verified === 0 || !user?.email_verified ? 2 : result || o.scanned ? 4 : 3;
  const steps = [t("onb.step1"), t("onb.step2"), t("onb.step3")];
  return (
    <div className="space-y-6">
      <header><h1 className="text-2xl font-bold">{t("onb.title")}</h1><p className="mt-1 text-muted-foreground">{t("onb.explain")}</p></header>
      <ol className="flex items-center gap-2" aria-label="Fortschritt">
        {steps.map((s, i) => (
          <li key={s} className="flex flex-1 items-center gap-2">
            <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold", step > i + 1 ? "bg-accent text-accent-foreground" : step === i + 1 ? "bg-primary text-primary-foreground" : "bg-muted")}
              aria-current={step === i + 1 ? "step" : undefined}>{step > i + 1 ? <Check className="h-4 w-4" /> : i + 1}</span>
            <span className="hidden text-sm sm:inline">{s}</span>
            {i < 2 && <span className="h-px flex-1 bg-border" />}
          </li>
        ))}
      </ol>
      {!user?.email_verified && (
        <Alert kind="warn">{t("next.verify_email")} <button className="underline" onClick={() => run(async () => { await api("/auth/resend-verification", { method: "POST" }); })}>Link erneut senden</button>
          {" · "}<a className="underline" href="/api/dev/outbox" target="_blank" rel="noreferrer">Dev-Postfach</a></Alert>
      )}
      {step <= 2 && <><p className="text-sm text-muted-foreground">{t("onb.verifyHint")}</p><Identifiers onChange={async () => { await home.reload(); await refresh(); }} /></>}
      {step === 3 && (
        <div className="rounded-lg border bg-card p-6 text-center">
          <p className="mb-4">{t("next.first_scan")}</p>
          <Button size="lg" disabled={busy} onClick={() => run(async () => { setResult(await api("/scan/run", { body: {} })); await home.reload(); })}>{busy ? t("scan.running") : t("onb.scanNow")}</Button>
        </div>
      )}
      {step === 4 && (
        <div className="space-y-3 rounded-lg border bg-card p-6 text-center">
          <p className="text-lg font-semibold">{t("onb.finished")}</p>
          {result && <p>{t("scan.done", { n: result.new })}</p>}
          <Link href="/app" className={buttonVariants({ size: "lg" })}>{t("nav.home")}</Link>
        </div>
      )}
      <ErrorNotice error={error} />
    </div>
  );
}
