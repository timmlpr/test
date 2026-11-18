"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert } from "@/components/ui/misc";
import { api } from "@/lib/api";

function Inner() {
  const token = useSearchParams().get("token") || "";
  const [s, setS] = useState<"wait" | "ok" | "fail">("wait");
  useEffect(() => { api("/profile/identifiers/verify-link", { body: { token } }).then(() => setS("ok")).catch(() => setS("fail")); }, [token]);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Adresse bestätigen</h1>
      {s === "wait" ? <p>…</p> : s === "ok" ? <Alert kind="ok">Bestätigt. Diese Adresse wird jetzt bei Scans berücksichtigt.</Alert>
        : <Alert kind="bad">Der Link ist ungültig, abgelaufen oder gehört zu einem anderen Konto. Bitte melde dich mit dem richtigen Konto an.</Alert>}
      <Link href="/app/profile" className="text-primary underline">Zum Profil</Link>
    </div>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }
