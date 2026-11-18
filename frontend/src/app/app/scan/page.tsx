"use client";
import { useState } from "react";
import { Radar } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/misc";
import { Badge } from "@/components/ui/badge";
import { ErrorNotice } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

export default function Scan() {
  const { t } = useT();
  const { user } = useAuth();
  const ids = useApi<any[]>("/profile/identifiers");
  const hist = useApi<any[]>("/scan/history");
  const [res, setRes] = useState<any>(null);
  const { run, busy, error } = useAction();
  const verified = (ids.data ?? []).filter((i) => i.verified);
  const go = (deep: boolean) => run(async () => { setRes(await api("/scan/run", { body: { deep } })); hist.reload(); });
  return (
    <div className="space-y-6">
      <PageHeader title={t("scan.title")} explain={t("scan.explain")} demo={user?.is_demo}
        next={res ? { label: t("nav.results"), href: "/app/results" } : { label: t("scan.basic"), onClick: () => go(false) }} />
      <Card>
        <CardHeader><CardTitle className="text-base">{t("scan.uses")}</CardTitle></CardHeader>
        <CardContent>
          {verified.length ? <div className="flex flex-wrap gap-2">{verified.map((i) => <Badge key={i.id} variant="muted">{t(`kind.${i.kind}`)}: {i.value}</Badge>)}</div>
            : <Alert kind="warn">{t("err.no_verified_identifiers")}</Alert>}
          <div className="mt-4 flex flex-wrap gap-3">
            <Button disabled={busy || !verified.length} onClick={() => go(false)}><Radar className="h-4 w-4" />{busy ? t("scan.running") : t("scan.basic")}</Button>
            <Button variant="outline" disabled={busy || !verified.length} onClick={() => go(true)}>{t("scan.deep")}</Button>
          </div>
        </CardContent>
      </Card>
      <ErrorNotice error={error} />
      {res && (
        <Alert kind="ok">
          <p className="font-medium">{t("scan.done", { n: res.new })}</p>
          <p className="text-sm">{t("scan.sources")}: {res.sources.join(", ") || "–"}</p>
          {res.errors?.length > 0 && <p className="text-sm">{t("scan.errors")}: {res.errors.map((e: any) => e.source).join(", ")}</p>}
        </Alert>
      )}
      <section>
        <h2 className="mb-2 font-semibold">{t("scan.history")}</h2>
        <ul className="divide-y rounded-lg border bg-card">
          {(hist.data ?? []).map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-2 p-3 text-sm">
              <span><Badge variant="muted">{s.kind}</Badge> {fmtDate(s.created_at, true)}</span>
              <span className="text-muted-foreground">{s.new} neu · {(s.summary?.sources ?? []).join(", ")}</span>
            </li>
          ))}
          {!hist.data?.length && <li className="p-3 text-sm text-muted-foreground">–</li>}
        </ul>
      </section>
    </div>
  );
}
