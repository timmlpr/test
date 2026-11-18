"use client";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, Progress, Tabs } from "@/components/ui/misc";
import { Badge } from "@/components/ui/badge";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { fmtDate } from "@/lib/utils";

/** Admin area: requires role=admin AND a session that passed TOTP (enforced server-side). */
export default function Admin() {
  const [tab, setTab] = useState("keys");
  const stats = useApi<any>("/admin/stats");
  if (stats.error) return <div><PageHeader title="Admin" explain="Nur für Administratoren mit 2-Faktor-Anmeldung." /><ErrorNotice error={stats.error} /></div>;
  return (
    <div className="space-y-6">
      <PageHeader title="Admin" explain="Schlüssel und Kontingente der Quellen, Warteliste, Missbrauchsmeldungen und Audit-Log." next={{ label: "Schlüssel prüfen", onClick: () => setTab("keys") }} />
      {stats.data && <div className="grid grid-cols-2 gap-3 sm:grid-cols-6">{Object.entries(stats.data).map(([k, v]: any) => <Card key={k} className="p-3"><p className="text-xs text-muted-foreground">{k}</p><p className="text-xl font-bold">{v}</p></Card>)}</div>}
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "keys", label: "Schlüssel & Quoten" }, { id: "wait", label: "Warteliste" }, { id: "abuse", label: "Missbrauch" }, { id: "feedback", label: "Feedback" }, { id: "audit", label: "Audit" }, { id: "locked", label: "Gesperrt" }]} />
      {tab === "keys" && <Keys />}{tab === "wait" && <Wait />}{tab === "abuse" && <List path="/admin/abuse" />}{tab === "feedback" && <List path="/admin/feedback" />}
      {tab === "audit" && <List path="/admin/audit" />}{tab === "locked" && <Locked />}
    </div>
  );
}

function Keys() {
  const { data, reload } = useApi<any[]>("/admin/sources");
  const [vals, setVals] = useState<Record<string, string>>({});
  const [res, setRes] = useState<Record<string, string>>({});
  const { run, error } = useAction();
  return (
    <div className="space-y-3">
      <ErrorNotice error={error} />
      {(data ?? []).map((s) => (
        <Card key={s.name}><CardContent className="space-y-2 pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{s.label}</span>
            <Badge variant={s.enabled ? "ok" : "muted"}>{s.enabled ? "aktiv" : "inaktiv"}</Badge>
            {s.paid && <Badge variant="warn">kostenpflichtig</Badge>}{s.requires_key && <Badge variant="outline">{s.has_key ? "Schlüssel hinterlegt" : "Schlüssel nötig"}</Badge>}
            <a href={s.terms_url} target="_blank" rel="noopener noreferrer" className="ml-auto text-xs text-primary underline">Nutzungsbedingungen</a>
          </div>
          <p className="text-xs text-muted-foreground">{s.notes} (geprüft {s.verified_on}) · Module: {s.modules.join(", ")} · Daten: {s.data_types.join(", ")}</p>
          <div className="flex items-center gap-2 text-xs"><span className="w-40">Heute: {s.used_today}/{s.rate_per_day} ({s.errors_today} Fehler)</span><Progress value={(s.used_today / s.rate_per_day) * 100} label="Kontingent" /></div>
          {s.requires_key && (
            <div className="flex flex-wrap gap-2">
              <Input type="password" placeholder={s.key_env ?? "API-Schlüssel"} value={vals[s.name] ?? ""} onChange={(e) => setVals({ ...vals, [s.name]: e.target.value })} className="max-w-sm" aria-label={`Schlüssel ${s.label}`} />
              <Button size="sm" onClick={() => run(async () => { await api(`/admin/keys/${s.name}`, { method: "PUT", body: { value: vals[s.name] } }); reload(); })} disabled={!vals[s.name]}>Speichern</Button>
              <Button size="sm" variant="outline" onClick={() => run(async () => { const r = await api<any>(`/admin/keys/${s.name}/test`, { method: "POST" }); setRes({ ...res, [s.name]: r.result }); })}>Testen</Button>
              {s.has_key && <Button size="sm" variant="ghost" onClick={() => run(async () => { await api(`/admin/keys/${s.name}`, { method: "DELETE" }); reload(); })}>Entfernen</Button>}
              {s.signup_url && <a className="self-center text-xs text-primary underline" href={s.signup_url} target="_blank" rel="noopener noreferrer">Schlüssel beantragen</a>}
            </div>
          )}
          {res[s.name] && <Alert kind={res[s.name] === "ok" ? "ok" : "warn"}>Test: {res[s.name]}</Alert>}
        </CardContent></Card>
      ))}
    </div>
  );
}

function Wait() {
  const { data, reload } = useApi<any[]>("/admin/waitlist");
  const [wave, setWave] = useState(1); const [cap, setCap] = useState(20);
  const { run, error } = useAction();
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-sm">Welle<Input type="number" value={wave} onChange={(e) => setWave(+e.target.value)} className="w-24" /></label>
        <label className="text-sm">Plätze<Input type="number" value={cap} onChange={(e) => setCap(+e.target.value)} className="w-24" /></label>
        <Button onClick={() => run(async () => { await api("/admin/waitlist/approve", { body: { wave, cap } }); reload(); })}>Welle freigeben</Button>
      </div>
      <ErrorNotice error={error} />
      <ul className="divide-y rounded-lg border bg-card text-sm">{(data ?? []).map((w) => (
        <li key={w.id} className="flex flex-wrap gap-2 p-2"><span className="flex-1">{w.email}</span><Badge variant={w.confirmed ? "ok" : "muted"}>{w.confirmed ? "bestätigt" : "offen"}</Badge>
          {w.approved && <Badge>Welle {w.wave}: {w.invite_code}</Badge>}<span className="text-muted-foreground">{fmtDate(w.created_at)}</span></li>))}</ul>
    </div>
  );
}

function List({ path }: { path: string }) {
  const { data } = useApi<any[]>(path);
  return <ul className="divide-y rounded-lg border bg-card text-sm">{(data ?? []).map((r, i) => <li key={i} className="p-2"><span className="text-muted-foreground">{fmtDate(r.at, true)}</span> · <code className="break-all text-xs">{JSON.stringify({ ...r, at: undefined })}</code></li>)}</ul>;
}

function Locked() {
  const { data, reload } = useApi<any[]>("/admin/users/locked");
  return <ul className="space-y-2">{(data ?? []).map((u) => <li key={u.id} className="flex items-center gap-2 rounded-lg border bg-card p-2 text-sm"><code>{u.id}</code> {u.reason}
    <Button size="sm" className="ml-auto" onClick={async () => { await api("/admin/users/unlock", { body: { user_id: u.id } }); reload(); }}>Entsperren</Button></li>)}</ul>;
}
