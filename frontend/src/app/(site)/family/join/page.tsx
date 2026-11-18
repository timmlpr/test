"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

function Inner() {
  const { t } = useT();
  const { user } = useAuth();
  const token = useSearchParams().get("token") || "";
  const [consent, setConsent] = useState(false);
  const [done, setDone] = useState(false);
  const { run, busy, error } = useAction();
  if (!user) return (
    <div className="space-y-3"><p>Melde dich an oder erstelle ein eigenes Konto, um beizutreten.</p>
      <Link className={buttonVariants()} href={`/login?next=${encodeURIComponent(`/family/join?token=${token}`)}`}>{t("auth.login.title")}</Link></div>
  );
  if (done) return <Alert kind="ok">Willkommen in der Familie! <Link href="/app" className="underline">Zur App</Link></Alert>;
  return (
    <div className="space-y-4">
      <Checkbox checked={consent} onChange={(e) => setConsent(e.target.checked)} label={t("fam.joinConsent")} />
      <ErrorNotice error={error} />
      <Button disabled={!consent || busy} onClick={() => run(async () => { await api("/family/join", { body: { token, consent } }); setDone(true); })}>{t("fam.join")}</Button>
    </div>
  );
}

export default function Join() {
  return <div className="container max-w-xl py-16"><h1 className="mb-6 text-2xl font-bold">Familie beitreten</h1><Suspense><Inner /></Suspense></div>;
}
