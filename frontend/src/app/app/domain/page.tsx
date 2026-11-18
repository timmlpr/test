"use client";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

const Yes = ({ ok }: { ok: boolean | null | undefined }) => <Badge variant={ok ? "ok" : ok === false ? "warn" : "muted"}>{ok ? "ja" : ok === false ? "nein" : "?"}</Badge>;

export default function Domain() {
  const { t } = useT();
  const [d, setD] = useState("");
  const [r, setR] = useState<any>(null);
  const { run, busy, error } = useAction();
  const young = r?.rdap?.age_days != null && r.rdap.age_days < 180;
  return (
    <div className="space-y-6">
      <PageHeader title={t("domain.title")} explain={t("domain.explain")} next={young ? { label: t("scam.title"), href: "/app/scam" } : undefined} />
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => setR(await api("/domain/check", { body: { domain: d } }))); }}>
        <Input value={d} onChange={(e) => setD(e.target.value)} placeholder={t("domain.input")} aria-label={t("domain.input")} required />
        <Button disabled={busy}>{t("domain.check")}</Button>
      </form>
      <ErrorNotice error={error} />
      {r && (
        <div className="grid gap-4 md:grid-cols-2">
          {young && <Alert kind="warn" className="md:col-span-2">Diese Domain ist erst {r.rdap.age_days} Tage alt. Bei Shops ist das ein Warnzeichen.</Alert>}
          <Card><CardHeader><CardTitle className="text-base">RDAP / WHOIS</CardTitle></CardHeader><CardContent className="space-y-1 text-sm">
            {r.rdap?.found === false ? <p>Nicht registriert.</p> : r.rdap ? <>
              <p>{t("domain.age")}: {r.rdap.age_days != null ? `${r.rdap.age_days} Tage (seit ${fmtDate(r.rdap.registered)})` : "unbekannt"}</p>
              <p>{t("domain.registrar")}: {r.rdap.registrar ?? "–"}</p><p>Läuft ab: {fmtDate(r.rdap.expires)}</p></> : <p>–</p>}
          </CardContent></Card>
          <Card><CardHeader><CardTitle className="text-base">{t("domain.tls")}</CardTitle></CardHeader><CardContent className="space-y-1 text-sm">
            <p>Gültig: <Yes ok={r.tls?.valid} /></p>{r.tls?.issuer && <p>Aussteller: {r.tls.issuer}</p>}{r.tls?.days_left != null && <p>Noch {r.tls.days_left} Tage gültig</p>}
          </CardContent></Card>
          <Card><CardHeader><CardTitle className="text-base">{t("domain.headers")} {r.header_score && `(${r.header_score.present}/${r.header_score.total})`}</CardTitle></CardHeader>
            <CardContent className="space-y-1 text-sm">{Object.entries(r.page?.headers ?? {}).map(([k, v]) => <p key={k} className="flex justify-between gap-2"><span className="font-mono text-xs">{k}</span><Yes ok={!!v} /></p>)}</CardContent></Card>
          <Card><CardHeader><CardTitle className="text-base">{t("domain.imprint")} & {t("domain.tech")}</CardTitle></CardHeader><CardContent className="space-y-1 text-sm">
            <p>Impressum gefunden: <Yes ok={!!r.page?.imprint_url} /></p>
            {r.imprint?.fetched && <><p>Anschrift: <Yes ok={r.imprint.has_address} /></p><p>E-Mail: <Yes ok={r.imprint.has_email} /></p><p>Handelsregister: <Yes ok={r.imprint.has_register} /></p></>}
            {r.imprint?.fetched === false && <p className="text-muted-foreground">Nicht abgerufen ({r.imprint.reason}).</p>}
            <p>{t("domain.tech")}: {(r.page?.tech ?? []).join(", ") || "–"}</p>
          </CardContent></Card>
          <Card><CardHeader><CardTitle className="text-base">{t("domain.mail")} & {t("domain.dns")}</CardTitle></CardHeader><CardContent className="space-y-1 text-sm">
            <p>SPF: <Yes ok={r.email_security?.spf} /> DMARC: <Yes ok={r.email_security?.dmarc} /></p>
            {Object.entries(r.dns ?? {}).map(([k, v]: any) => v.length ? <p key={k} className="break-all"><span className="font-mono text-xs">{k}</span>: {v.slice(0, 3).join(", ")}</p> : null)}
          </CardContent></Card>
          <Card><CardHeader><CardTitle className="text-base">{t("domain.wayback")}</CardTitle></CardHeader><CardContent className="text-sm">
            <p>{r.wayback?.first ? fmtDate(r.wayback.first) : "–"}</p>{r.wayback?.link && <a className="text-primary underline" href={r.wayback.link} target="_blank" rel="noopener noreferrer">Archiv ansehen</a>}
          </CardContent></Card>
          {r.errors?.length > 0 && <Alert kind="warn" className="md:col-span-2">{t("err.source_unavailable")} ({r.errors.map((e: any) => e.source).join(", ")})</Alert>}
        </div>
      )}
    </div>
  );
}
