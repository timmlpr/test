"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { FileSpreadsheet } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api, download } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { eur, fmtDate } from "@/lib/utils";

function Subs() {
  const { t } = useT();
  const { data, error, reload } = useApi<any>("/subs");
  const { run, busy, error: e2 } = useAction();
  if (error) return <div><PageHeader title={t("subs.title")} explain={t("subs.explain")} premium /><ErrorNotice error={error} /></div>;
  const connected = useSearchParams().get("mailbox") === "connected";
  const mb = data?.mailbox;
  const upload = (f: File) => run(async () => { const fd = new FormData(); fd.append("file", f); await api("/subs/upload", { form: fd }); reload(); });
  return (
    <div className="space-y-6">
      <PageHeader title={t("subs.title")} explain={t("subs.explain")} premium next={data?.items.length ? { label: "Excel-Export", onClick: () => download("/subs/xlsx", "abos.xlsx") } : undefined} />
      <Card><CardContent className="space-y-3 pt-5">
        <label className="block text-sm font-medium" htmlFor="mbox">{t("subs.upload")}</label>
        <input id="mbox" type="file" accept=".mbox,.eml,.zip" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
          className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-primary-foreground" />
        <details className="text-sm"><summary className="cursor-pointer text-primary">{t("subs.howto")}</summary>
          <ul className="mt-2 list-disc pl-5 text-muted-foreground"><li>Gmail: takeout.google.com → nur „Mail“ wählen → .mbox</li><li>Thunderbird: Rechtsklick auf Ordner → „Exportieren“ bzw. Add-on ImportExportTools NG</li>
            <li>Outlook/Apple Mail: einzelne Mails als .eml speichern und als .zip hochladen</li></ul></details>
        <div className="space-y-2 border-t pt-3">
          <p className="text-sm font-medium">{t("subs.mailboxTitle")}</p>
          <p className="text-xs text-muted-foreground">{t("subs.mailboxHint")}</p>
          {connected && <Alert kind="ok">{t("subs.mailboxConnected")}</Alert>}
          {mb?.connected ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant="ok">{mb.address ?? "Gmail"}</Badge>
              <span className="text-xs text-muted-foreground">{t("subs.mailboxLast")}: {fmtDate(mb.last_sync, true)}</span>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => run(async () => { await api("/subs/mailbox/sync", { method: "POST" }); reload(); })}>{t("subs.mailboxSync")}</Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(async () => { await api("/subs/mailbox", { method: "DELETE" }); reload(); })}>{t("subs.mailboxDisconnect")}</Button>
            </div>
          ) : mb?.available ? (
            <a href="/api/subs/mailbox/start" className="inline-block text-sm font-medium text-primary underline">{t("subs.mailboxConnect")}</a>
          ) : (
            <p className="text-xs text-muted-foreground">{t("subs.oauth")}</p>
          )}
        </div>
        <ErrorNotice error={e2} />
      </CardContent></Card>
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Card className="p-4"><p className="text-xs text-muted-foreground">{t("subs.monthly")}</p><p className="text-2xl font-bold">{eur(data.monthly_cost)}</p></Card>
            {["subscription", "newsletter", "account"].map((c) => <Card key={c} className="p-4"><p className="text-xs text-muted-foreground">{t(`subs.${c}`)}</p><p className="text-2xl font-bold">{data.counts[c]}</p></Card>)}
          </div>
          {data.items.length > 0 && <Button variant="outline" size="sm" onClick={() => download("/subs/xlsx", "abos.xlsx")}><FileSpreadsheet className="h-4 w-4" />Excel</Button>}
          <ul className="space-y-2">{data.items.map((s: any) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3 text-sm">
              <Badge variant={s.category === "subscription" ? "default" : "muted"}>{t(`subs.${s.category}`)}</Badge>
              <span className="font-medium">{s.sender}</span><span className="text-muted-foreground">{s.domain}</span>
              {s.amount != null && <span className="font-semibold">{eur(s.amount)} / {s.interval === "year" ? "Jahr" : "Monat"}</span>}
              <span className="text-xs text-muted-foreground">{s.count} Mails · zuletzt {fmtDate(s.last_seen)}</span>
              <span className="ml-auto flex gap-3">
                {s.unsubscribe && <a href={s.unsubscribe} target="_blank" rel="noopener noreferrer" className="text-primary underline">{t("subs.unsubscribe")}</a>}
                <Link href={`/app/requests/new`} className="text-primary underline">{t("subs.deleteAccount")}</Link>
              </span>
            </li>))}
          </ul>
          {!data.items.length && <Alert>Noch nichts analysiert. Lade einen Mail-Export hoch.</Alert>}
        </>
      )}
    </div>
  );
}

export default function Page() { return <Suspense><Subs /></Suspense>; }
