"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Textarea } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

/** Kündigungsbutton (§ 312k BGB): reachable without login, two clear steps, immediate confirmation. */
export default function Kuendigen() {
  const { t } = useT();
  const [f, setF] = useState({ email: "", name: "", contract: "", extraordinary: false, reason: "" });
  const [step, setStep] = useState<"form" | "confirm" | "done">("form");
  const { run, busy, error } = useAction();
  return (
    <div className="container max-w-xl py-12">
      <h1 className="text-3xl font-bold">{t("cancel.title")}</h1>
      <p className="mt-2 text-muted-foreground">{t("cancel.explain")}</p>
      {step === "done" ? <Alert kind="ok" className="mt-6">{t("cancel.done")}</Alert> : (
        <form className="mt-6 space-y-4" onSubmit={(e) => { e.preventDefault(); if (step === "form") setStep("confirm"); else run(async () => { await api("/billing/cancel-request", { body: f }); setStep("done"); }); }}>
          <Field label="Name" htmlFor="c-name"><Input id="c-name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="name" /></Field>
          <Field label={t("auth.email")} htmlFor="c-email"><Input id="c-email" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoComplete="email" /></Field>
          <Field label="Vertrag (optional)" htmlFor="c-contract"><Input id="c-contract" value={f.contract} onChange={(e) => setF({ ...f, contract: e.target.value })} placeholder="z. B. Premium monatlich" /></Field>
          <Checkbox checked={f.extraordinary} onChange={(e) => setF({ ...f, extraordinary: e.target.checked })} label="Außerordentliche Kündigung" />
          {f.extraordinary && <Field label="Grund" htmlFor="c-reason"><Textarea id="c-reason" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>}
          <ErrorNotice error={error} />
          {step === "confirm" && <Alert kind="warn">Bitte bestätige: Du möchtest deinen Vertrag kündigen.</Alert>}
          <Button type="submit" variant={step === "confirm" ? "destructive" : "default"} disabled={busy} className="w-full">
            {step === "confirm" ? t("cancel.button") : "Weiter zur Bestätigung"}
          </Button>
        </form>
      )}
    </div>
  );
}
