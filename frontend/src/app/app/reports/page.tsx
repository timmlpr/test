"use client";
import { useState } from "react";
import { FileDown, FileSpreadsheet, Lock } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/misc";
import { Select } from "@/components/ui/input";
import { ErrorNotice } from "@/components/notice";
import { api, download } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { plans } from "@/lib/brand";
import { useT } from "@/lib/i18n";
import { eur, fmtDate } from "@/lib/utils";

export default function Reports() {
  const { t } = useT();
  const prev = useApi<any>("/reports/preview");
  const list = useApi<any[]>("/reports");
  const { run, busy, error } = useAction();
  const [a, setA] = useState(""); const [b, setB] = useState("");
  const [cmp, setCmp] = useState<any>(null);
  const s = prev.data?.summary;
  const unlocked = prev.data?.unlocked;
  const buy = () => run(async () => { const r = await api<any>("/billing/checkout", { body: { product: "one_time_report" } }); location.href = r.url; });
  const create = () => run(async () => { await api("/reports", { method: "POST" }); list.reload(); prev.reload(); });
  return (
    <div className="space-y-6">
      <PageHeader title={t("rep.title")} explain={t("rep.explain")}
        next={unlocked ? { label: t("rep.create"), onClick: create } : { label: t("rep.buy", { price: eur(plans.one_time_report.price) }), onClick: buy }} />
      <Card>
        <CardHeader><CardTitle className="text-base">{t("rep.preview")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {s && <p className="text-lg">{t("rep.previewText", { total: s.total, high: s.high, breaches: s.breaches })} Risiko-Wert {s.score}/100.</p>}
          {!unlocked && <Alert><Lock className="mr-1 inline h-4 w-4" />{t("rep.locked")}</Alert>}
          <div className="flex flex-wrap gap-2">
            {unlocked ? <Button onClick={create} disabled={busy}>{t("rep.create")}</Button> : <>
              <Button onClick={buy} disabled={busy}>{t("rep.buy", { price: eur(plans.one_time_report.price) })}</Button>
              <Button variant="outline" onClick={() => (location.href = "/app/billing")}>{t("gate.cta")}</Button></>}
          </div>
          <ErrorNotice error={error} />
        </CardContent>
      </Card>
      {!!list.data?.length && (
        <Card>
          <CardHeader><CardTitle className="text-base">{t("rep.list")}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <ul className="divide-y">
              {list.data.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <span className="font-medium">{t("rep.version")} {r.version}</span><span className="text-muted-foreground">{fmtDate(r.created_at, true)} · {r.summary.score}/100 · {r.summary.total} Funde</span>
                  <span className="ml-auto flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => download(`/reports/${r.id}/pdf`, `tracelow-report-v${r.version}.pdf`)}><FileDown className="h-4 w-4" />PDF</Button>
                    <Button size="sm" variant="outline" onClick={() => download(`/reports/${r.id}/xlsx`, `tracelow-report-v${r.version}.xlsx`)}><FileSpreadsheet className="h-4 w-4" />Excel</Button>
                  </span>
                </li>
              ))}
            </ul>
            {list.data.length > 1 && (
              <div className="flex flex-wrap items-end gap-2 border-t pt-3">
                <Select value={a} onChange={(e) => setA(e.target.value)} className="w-40" aria-label="Vorher"><option value="">Vorher …</option>{list.data.map((r) => <option key={r.id} value={r.id}>V{r.version}</option>)}</Select>
                <Select value={b} onChange={(e) => setB(e.target.value)} className="w-40" aria-label="Nachher"><option value="">Nachher …</option>{list.data.map((r) => <option key={r.id} value={r.id}>V{r.version}</option>)}</Select>
                <Button size="sm" disabled={!a || !b} onClick={async () => setCmp(await api(`/reports/compare/${a}/${b}`))}>{t("rep.compare")}</Button>
              </div>
            )}
            {cmp && (
              <Alert kind={cmp.score_delta <= 0 ? "ok" : "warn"}>
                <p>Risiko-Wert: {cmp.before.score} → {cmp.after.score} ({cmp.score_delta > 0 ? "+" : ""}{cmp.score_delta})</p>
                <p>{t("rep.resolved")}: {cmp.resolved.length} · {t("rep.added")}: {cmp.added.length}</p>
              </Alert>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
