"use client";
import { useState } from "react";
import { Lock, Unlock } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { decryptVault, encryptVault } from "@/lib/vault-crypto";
import { fmtDate } from "@/lib/utils";

const TEMPLATE = "Konten:\n- E-Mail: …\n- Bank: …\n- Social Media: … (Wunsch: löschen / Gedenkzustand)\n\nNotfall-Infos:\n- Versicherungen: …\n- Wo liegen wichtige Unterlagen: …\n";

export default function Estate() {
  const { t } = useT();
  const { data, error, reload } = useApi<any>("/estate");
  const [pass, setPass] = useState("");
  const [plain, setPlain] = useState<string | null>(null);
  const [trusted, setTrusted] = useState<string | null>(null);
  const [delay, setDelay] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const { run, busy, error: e2 } = useAction();
  if (error) return <div><PageHeader title={t("estate.title")} explain={t("estate.explain")} premium /><ErrorNotice error={error} /></div>;
  if (!data) return null;
  const unlocked = plain !== null;
  return (
    <div className="space-y-6">
      <PageHeader title={t("estate.title")} explain={t("estate.explain")} premium next={!unlocked ? { label: t("estate.unlock"), href: "#pass" } : undefined} />
      {data.unlock_requested_at && <Alert kind="warn">{t("estate.requested", { date: fmtDate(data.unlock_requested_at) })}{" "}
        <button className="underline" onClick={() => run(async () => { await api("/estate/veto", { method: "POST" }); reload(); })}>{t("estate.veto")}</button></Alert>}
      <Card><CardContent className="space-y-4 pt-5">
        {!unlocked ? (
          <form id="pass" className="space-y-3" onSubmit={(e) => { e.preventDefault(); run(async () => {
            if (!data.ciphertext) { setPlain(TEMPLATE); return; }
            try { setPlain(await decryptVault(data, pass)); } catch { setMsg("Kennwort falsch."); }
          }); }}>
            <Field label={t("estate.passphrase")} htmlFor="pp" hint={data.ciphertext ? undefined : "Wähle ein neues, langes Kennwort. Ohne dieses Kennwort kann niemand – auch wir nicht – den Inhalt lesen."}>
              <Input id="pp" type="password" minLength={10} required value={pass} onChange={(e) => setPass(e.target.value)} autoComplete="new-password" />
            </Field>
            <Button><Unlock className="h-4 w-4" />{t("estate.unlock")}</Button>
            {msg && <Alert kind="bad">{msg}</Alert>}
          </form>
        ) : (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => {
            const enc = await encryptVault(plain!, pass);
            await api("/estate", { method: "PUT", body: { ...enc, trusted_email: (trusted ?? data.trusted_email) || null, unlock_delay_days: delay ?? data.unlock_delay_days } });
            setMsg("Verschlüsselt gespeichert."); reload();
          }); }}>
            <Textarea rows={12} value={plain!} onChange={(e) => setPlain(e.target.value)} className="font-mono text-sm" aria-label="Tresor-Inhalt" />
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("estate.trusted")} htmlFor="tr"><Input id="tr" type="email" value={trusted ?? data.trusted_email ?? ""} onChange={(e) => setTrusted(e.target.value)} /></Field>
              <Field label={t("estate.delay")} htmlFor="dl"><Input id="dl" type="number" min={3} max={365} value={delay ?? data.unlock_delay_days} onChange={(e) => setDelay(+e.target.value)} /></Field>
            </div>
            <p className="text-xs text-muted-foreground">{t("estate.note")}</p>
            <div className="flex gap-2"><Button disabled={busy}><Lock className="h-4 w-4" />{t("estate.save")}</Button><Button type="button" variant="outline" onClick={() => { setPlain(null); setPass(""); }}>Sperren</Button></div>
            {msg && <Alert kind="ok">{msg}</Alert>}
          </form>
        )}
        <ErrorNotice error={e2} />
      </CardContent></Card>
    </div>
  );
}
