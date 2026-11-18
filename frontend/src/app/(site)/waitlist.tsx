"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox, Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

export function Waitlist() {
  const { t } = useT();
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [hp, setHp] = useState("");
  const [done, setDone] = useState(false);
  const { run, busy, error } = useAction();
  return (
    <div className="mx-auto max-w-xl rounded-2xl border bg-card p-6 text-center shadow-sm sm:p-10">
      <h2 className="text-2xl font-bold">{t("landing.wait.title")}</h2>
      <p className="mt-2 text-muted-foreground">{t("landing.wait.sub")}</p>
      {done ? <Alert kind="ok" className="mt-6 text-left">{t("landing.wait.done")}</Alert> : (
        <form className="mt-6 space-y-3 text-left" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/waitlist", { body: { email, consent, website: hp } }); setDone(true); }); }}>
          <label className="sr-only" htmlFor="wl-email">{t("auth.email")}</label>
          <Input id="wl-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@beispiel.de" autoComplete="email" />
          <input type="text" tabIndex={-1} autoComplete="off" value={hp} onChange={(e) => setHp(e.target.value)} className="hidden" aria-hidden="true" name="website" />
          <Checkbox checked={consent} onChange={(e) => setConsent(e.target.checked)} label={t("landing.wait.consent")} required />
          <ErrorNotice error={error} />
          <Button type="submit" className="w-full" disabled={busy}>{t("landing.wait.button")}</Button>
        </form>
      )}
    </div>
  );
}
