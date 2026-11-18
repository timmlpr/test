"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

function Inner() {
  const { t } = useT();
  const token = useSearchParams().get("token") || "";
  const [pw, setPw] = useState("");
  const [done, setDone] = useState(false);
  const { run, busy, error } = useAction();
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/auth/password-reset/confirm", { body: { token, password: pw } }); setDone(true); }); }}>
      <h1 className="text-2xl font-bold">{t("auth.reset.title")}</h1>
      {done ? <Alert kind="ok">{t("auth.reset.done")} <Link href="/login" className="underline">{t("auth.login.title")}</Link></Alert> : <>
        <Field label={t("auth.password")} htmlFor="n-pw" hint={t("auth.register.pwHint")}><Input id="n-pw" type="password" minLength={10} required autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
        <ErrorNotice error={error} />
        <Button className="w-full" disabled={busy}>{t("common.save")}</Button>
      </>}
    </form>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }
