"use client";
import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

/** Shown only when no Stripe key is configured and DEMO_MODE is on. No money moves. */
function Demo() {
  const { t } = useT();
  const token = useSearchParams().get("token") || "";
  const router = useRouter();
  const { refresh } = useAuth();
  const { run, busy, error } = useAction();
  return (
    <div className="max-w-lg space-y-4">
      <PageHeader title="Demo-Kasse" explain={t("bill.demo")} />
      <Alert kind="warn">Stripe ist noch nicht verbunden. Diese Seite simuliert die Zahlung, damit du alle Premium-Funktionen ausprobieren kannst.</Alert>
      <ErrorNotice error={error} />
      <div className="flex gap-2">
        <Button disabled={busy} onClick={() => run(async () => { await api("/billing/demo/complete", { body: { token } }); await refresh(); router.push("/app/billing?status=success"); })}>{t("bill.demoConfirm")}</Button>
        <Button variant="outline" onClick={() => router.push("/app/billing")}>{t("common.cancel")}</Button>
      </div>
    </div>
  );
}
export default function Page() { return <Suspense><Demo /></Suspense>; }
