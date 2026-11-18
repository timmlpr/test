"use client";
import { Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Empty } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

const SENS: Record<string, string> = { iban: "Bankverbindung", tax_id: "Steuer-ID", social_security: "Sozialversicherungsnr.", health: "Gesundheitsdaten", birthdate: "Geburtsdatum" };

export default function Documents() {
  const { t } = useT();
  const { data, error, reload } = useApi<any>("/documents");
  const { run, busy, error: e2 } = useAction();
  if (error) return <div><PageHeader title={t("docs.title")} explain={t("docs.explain")} premium /><ErrorNotice error={error} /></div>;
  const nextRem = data?.reminders?.[0];
  return (
    <div className="space-y-6">
      <PageHeader title={t("docs.title")} explain={t("docs.explain")} premium next={nextRem ? { label: `${nextRem.title} – ${fmtDate(nextRem.due_at)}`, href: "#reminders" } : undefined} />
      <Card><CardContent className="space-y-2 pt-5">
        <label htmlFor="doc" className="text-sm font-medium">{t("docs.upload")}</label>
        <input id="doc" type="file" accept=".pdf,.txt,image/*" disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) run(async () => { const fd = new FormData(); fd.append("file", f); await api("/documents", { form: fd }); reload(); }); }}
          className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-primary-foreground" />
        <ErrorNotice error={e2} />
      </CardContent></Card>
      {!!data?.reminders?.length && <Card id="reminders"><CardHeader><CardTitle className="text-base">{t("docs.reminders")}</CardTitle></CardHeader><CardContent>
        <ul className="space-y-1 text-sm">{data.reminders.map((r: any) => <li key={r.id}>{fmtDate(r.due_at)} – {r.title}</li>)}</ul></CardContent></Card>}
      {!data?.items.length ? <Empty title="Noch keine Dokumente." /> : (
        <ul className="space-y-3">{data.items.map((d: any) => (
          <li key={d.id} className="rounded-lg border bg-card p-4">
            <div className="flex items-center gap-2"><span className="font-medium">{d.title}</span><span className="text-xs text-muted-foreground">{fmtDate(d.created_at)}</span>
              <button className="ml-auto rounded p-1.5 hover:bg-muted" aria-label={`${t("common.delete")}: ${d.title}`} onClick={() => run(async () => { await api(`/documents/${d.id}`, { method: "DELETE" }); reload(); })}><Trash2 className="h-4 w-4" /></button></div>
            {d.deadlines.length > 0 && <div className="mt-2 text-sm"><p className="font-medium">{t("docs.deadlines")}:</p><ul className="list-disc pl-5">{d.deadlines.map((x: any) => <li key={x.date + x.context}>{fmtDate(x.date)} – „{x.context}“</li>)}</ul></div>}
            {d.sensitive.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{d.sensitive.map((s: string) => <Badge key={s} variant="warn">{SENS[s] ?? s}</Badge>)}</div>}
          </li>))}
        </ul>
      )}
    </div>
  );
}
