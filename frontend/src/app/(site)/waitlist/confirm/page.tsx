"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert } from "@/components/ui/misc";
import { api } from "@/lib/api";

function Inner() {
  const token = useSearchParams().get("token") || "";
  const [state, setState] = useState<"wait" | "ok" | "fail">("wait");
  useEffect(() => { api("/waitlist/confirm", { body: { token } }).then(() => setState("ok")).catch(() => setState("fail")); }, [token]);
  return state === "wait" ? <p>Einen Moment …</p> : state === "ok"
    ? <Alert kind="ok">Danke! Du stehst jetzt auf der Warteliste. Wir melden uns, sobald deine Welle startet.</Alert>
    : <Alert kind="bad">Der Link ist ungültig oder abgelaufen.</Alert>;
}

export default function Confirm() {
  return <div className="container max-w-xl py-16"><h1 className="mb-6 text-2xl font-bold">Warteliste</h1><Suspense><Inner /></Suspense></div>;
}
