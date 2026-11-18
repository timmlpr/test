"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { decryptVault } from "@/lib/vault-crypto";
import { fmtDate } from "@/lib/utils";

function Inner() {
  const token = useSearchParams().get("token") || "";
  const [res, setRes] = useState<any>(null);
  const [pass, setPass] = useState("");
  const [plain, setPlain] = useState<string | null>(null);
  const { run, busy, error } = useAction();
  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">Du wurdest als Vertrauensperson benannt. Die Person wird über deine Anfrage informiert und kann widersprechen. Nach Ablauf der Wartezeit siehst du den verschlüsselten Inhalt; zum Lesen brauchst du das Kennwort, das sie dir gegeben hat.</p>
      <Button disabled={busy} onClick={() => run(async () => setRes(await api("/estate/unlock-request", { body: { token } })))}>Freigabe anfragen / Status prüfen</Button>
      <ErrorNotice error={error} />
      {res?.status === "waiting" && <Alert>Angefragt. Freigabe frühestens am {fmtDate(res.release_at)}.</Alert>}
      {res?.status === "released" && (
        <div className="space-y-3">
          <Input type="password" value={pass} onChange={(e) => setPass(e.target.value)} placeholder="Tresor-Kennwort" aria-label="Tresor-Kennwort" />
          <Button onClick={async () => { try { setPlain(await decryptVault(res, pass)); } catch { setPlain("Kennwort falsch."); } }}>Entschlüsseln</Button>
          {plain && <pre className="whitespace-pre-wrap rounded-md border bg-card p-4 text-sm">{plain}</pre>}
        </div>
      )}
    </div>
  );
}

export default function EstateRequest() {
  return <div className="container max-w-xl py-16"><h1 className="mb-6 text-2xl font-bold">Digitaler Nachlass</h1><Suspense><Inner /></Suspense></div>;
}
