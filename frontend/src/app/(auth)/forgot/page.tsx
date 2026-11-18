"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

export default function Forgot() {
  const { t } = useT();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const { run, busy } = useAction();
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/auth/password-reset", { body: { email } }); setSent(true); }); }}>
      <h1 className="text-2xl font-bold">{t("auth.forgot.title")}</h1>
      <p className="text-sm text-muted-foreground">{t("auth.forgot.sub")}</p>
      {sent ? <Alert kind="ok">{t("auth.forgot.sent")}</Alert> : <>
        <Field label={t("auth.email")} htmlFor="f-email"><Input id="f-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Button className="w-full" disabled={busy}>{t("common.next")}</Button>
      </>}
    </form>
  );
}
