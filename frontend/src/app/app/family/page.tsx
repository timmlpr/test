"use client";
import { useState } from "react";
import { Copy } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Field, Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { Badge } from "@/components/ui/badge";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

export default function Family() {
  const { t } = useT();
  const fam = useApi<any>("/family");
  const [label, setLabel] = useState("");
  const [child, setChild] = useState({ label: "", login_email: "", password: "", birth_year: 2014, guardian_consent: false });
  const { run, busy, error } = useAction();
  const d = fam.data;
  if (d && d.role !== "owner") return (
    <div>
      <PageHeader title={t("fam.title")} explain={t("fam.explain")} next={{ label: t("gate.cta"), href: "/app/billing#plans" }} />
      {d.role === "member" ? <Alert kind="ok">Du bist Mitglied einer Familie. <button className="underline" onClick={() => run(async () => { await api("/family/leave", { method: "POST" }); fam.reload(); })}>Familie verlassen</button></Alert>
        : <Alert>Mit dem Familien-Tarif schützt du bis zu 6 Personen – jede mit eigenem Login.</Alert>}
    </div>
  );
  return (
    <div className="space-y-6">
      <PageHeader title={t("fam.title")} explain={t("fam.explain")} next={{ label: t("fam.invite"), href: "#invite" }} />
      {d && <p className="text-sm">{t("fam.seats", { used: d.used, seats: d.seats })}</p>}
      <ul className="space-y-2">
        {d?.members.map((m: any) => (
          <li key={m.id} className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3">
            <span className="font-medium">{m.label}</span>{m.is_child && <Badge variant="muted">Kind</Badge>}<Badge variant={m.status === "active" ? "ok" : "warn"}>{m.status}</Badge>
            {m.invite_link && <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(m.invite_link)}><Copy className="h-4 w-4" />Link</Button>}
            <Button size="sm" variant="ghost" className="ml-auto" onClick={() => run(async () => { await api(`/family/members/${m.id}`, { method: "DELETE" }); fam.reload(); })}>{t("common.delete")}</Button>
          </li>
        ))}
      </ul>
      <ErrorNotice error={error} />
      <div className="grid gap-4 md:grid-cols-2">
        <Card id="invite"><CardHeader><CardTitle className="text-base">{t("fam.invite")}</CardTitle></CardHeader>
          <CardContent><form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/family/invite", { body: { label } }); setLabel(""); fam.reload(); }); }}>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} required placeholder="Name" aria-label="Name" /><Button disabled={busy}>{t("fam.invite")}</Button></form>
            <p className="mt-2 text-xs text-muted-foreground">Die Person bekommt einen Link, legt ein eigenes Konto an und stimmt selbst zu.</p></CardContent></Card>
        <Card><CardHeader><CardTitle className="text-base">{t("fam.child")}</CardTitle></CardHeader>
          <CardContent><form className="space-y-3" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/family/child", { body: child }); fam.reload(); }); }}>
            <Field label="Name" htmlFor="cn"><Input id="cn" required value={child.label} onChange={(e) => setChild({ ...child, label: e.target.value })} /></Field>
            <Field label="Login-E-Mail des Kindes" htmlFor="ce"><Input id="ce" type="email" required value={child.login_email} onChange={(e) => setChild({ ...child, login_email: e.target.value })} /></Field>
            <Field label={t("auth.password")} htmlFor="cp"><Input id="cp" type="password" minLength={10} required value={child.password} onChange={(e) => setChild({ ...child, password: e.target.value })} /></Field>
            <Field label="Geburtsjahr" htmlFor="cy"><Input id="cy" type="number" min={2008} max={2030} value={child.birth_year} onChange={(e) => setChild({ ...child, birth_year: +e.target.value })} /></Field>
            <Checkbox checked={child.guardian_consent} onChange={(e) => setChild({ ...child, guardian_consent: e.target.checked })} label={t("fam.childConsent")} />
            <Button disabled={busy || !child.guardian_consent}>{t("fam.child")}</Button></form></CardContent></Card>
      </div>
    </div>
  );
}
