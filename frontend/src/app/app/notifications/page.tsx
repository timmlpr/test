"use client";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { RiskBadge } from "@/components/ui/badge";
import { Empty } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

export default function Notifications() {
  const { t } = useT();
  const { data, reload } = useApi<any>("/notifications");
  return (
    <div>
      <PageHeader title={t("notif.title")} explain="Hinweise zu neuen Funden, Fristen und deinem Konto." next={data?.unread ? { label: t("notif.readAll"), onClick: async () => { await api("/notifications/read", { method: "POST" }); reload(); } } : undefined} />
      {!data?.items.length ? <Empty title={t("notif.empty")} /> : (
        <ul className="space-y-2">{data.items.map((n: any) => (
          <li key={n.id} className={`rounded-lg border bg-card p-4 ${n.read ? "opacity-70" : ""}`}>
            <div className="flex items-center gap-2"><RiskBadge risk={n.severity} label={t(`risk.${n.severity}`)} /><span className="font-medium">{n.title}</span><span className="ml-auto text-xs text-muted-foreground">{fmtDate(n.created_at, true)}</span></div>
            <p className="mt-1 text-sm text-muted-foreground">{n.body}</p>
            {n.link && <Link href={n.link} className="mt-1 inline-block text-sm text-primary underline">{t("common.open")}</Link>}
          </li>))}
        </ul>
      )}
      {!!data?.unread && <Button variant="outline" className="mt-4" onClick={async () => { await api("/notifications/read", { method: "POST" }); reload(); }}>{t("notif.readAll")}</Button>}
    </div>
  );
}
