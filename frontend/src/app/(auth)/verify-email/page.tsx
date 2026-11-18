"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert } from "@/components/ui/misc";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

function Inner() {
  const { t } = useT();
  const { refresh } = useAuth();
  const token = useSearchParams().get("token") || "";
  const [s, setS] = useState<"wait" | "ok" | "fail">("wait");
  useEffect(() => { api("/auth/verify-email", { body: { token } }).then(async () => { setS("ok"); await refresh(); }).catch(() => setS("fail")); }, [token, refresh]);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">E-Mail bestätigen</h1>
      {s === "wait" ? <p>…</p> : s === "ok" ? <Alert kind="ok">{t("auth.verify.ok")}</Alert> : <Alert kind="bad">{t("auth.verify.fail")}</Alert>}
      {s === "ok" && <Link href="/app/onboarding" className="text-primary underline">{t("common.next")}</Link>}
    </div>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }
