"use client";
import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Alert, Empty } from "@/components/ui/misc";
import { FindingRow, RequestLink, type Finding } from "@/components/app/finding";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

export default function Breaches() {
  const { t } = useT();
  const { data, reload } = useApi<{ items: Finding[]; remaining: number }>("/breach");
  const [res, setRes] = useState<any>(null);
  const { run, busy, error } = useAction();
  const check = () => run(async () => { setRes(await api("/breach/check", { method: "POST" })); reload(); });
  const pw = data?.items.find((f) => f.data_types.includes("password") && f.status === "open");
  return (
    <div>
      <PageHeader title={t("breach.title")} explain={t("breach.explain")}
        next={pw ? { label: t("act.change_password_everywhere"), href: "/app/passwords" } : { label: t("breach.check"), onClick: check }} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button onClick={check} disabled={busy}>{t("breach.check")}</Button>
        {data && <span className="text-sm text-muted-foreground">{t("breach.remaining", { n: Math.max(0, data.remaining) })}</span>}
      </div>
      <ErrorNotice error={error} />
      {res?.errors?.length > 0 && <Alert kind="warn" className="mb-3">{t("err.source_unavailable")}</Alert>}
      {!data?.items.length ? <Empty icon={<ShieldCheck className="h-8 w-8" />} title={t("breach.none")} /> : (
        <ul className="space-y-3">
          {data.items.map((f) => (
            <FindingRow key={f.id} f={f} actions={<div className="w-full space-y-2">
              {f.details?.description && <p className="text-sm text-muted-foreground">{f.details.description}</p>}
              <p className="text-sm font-medium">{t("breach.actions")}:</p>
              <ul className="list-disc pl-5 text-sm">{(f.details?.actions ?? []).map((a: string) => <li key={a}>{t(`act.${a}`)}</li>)}</ul>
              <RequestLink f={f} />
            </div>} />
          ))}
        </ul>
      )}
    </div>
  );
}
