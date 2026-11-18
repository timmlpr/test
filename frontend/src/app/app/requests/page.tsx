"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Copy, FileDown, Mail, Plus } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/input";
import { Alert, Empty } from "@/components/ui/misc";
import { api, download } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

function Requests() {
  const { t } = useT();
  const focus = useSearchParams().get("id");
  const { data, reload } = useApi<any[]>("/requests");
  const [open, setOpen] = useState<string | null>(focus);
  const [copied, setCopied] = useState<string | null>(null);
  const set = async (id: string, body: any) => { await api(`/requests/${id}`, { method: "PATCH", body }); reload(); };
  const overdue = data?.find((r) => r.overdue);
  return (
    <div>
      <PageHeader title={t("req.title")} explain={t("req.explain")}
        next={overdue ? { label: `${t("next.follow_up_request")} (${overdue.recipient})`, onClick: () => setOpen(overdue.id) } : { label: t("req.new"), href: "/app/requests/new" }} />
      <Alert className="mb-4">{t("req.disclaimer")}</Alert>
      <Link href="/app/requests/new" className={buttonVariants({ className: "mb-4" })}><Plus className="h-4 w-4" />{t("req.new")}</Link>
      {!data?.length ? <Empty icon={<Mail className="h-8 w-8" />} title={t("req.empty")} /> : (
        <ul className="space-y-3">
          {data.map((r) => (
            <li key={r.id} className="rounded-lg border bg-card p-4">
              <button className="flex w-full flex-wrap items-center gap-2 text-left" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
                <Badge variant="muted">{r.kind.toUpperCase().replace("ART", "Art. ")}</Badge>
                <span className="flex-1 font-medium">{r.recipient}</span>
                <Badge variant={r.status === "done" ? "ok" : r.overdue ? "bad" : r.status === "sent" ? "default" : "muted"}>{t(`req.status.${r.status}`)}</Badge>
                {r.status === "sent" && <span className="text-xs text-muted-foreground">{t("req.due")}: {fmtDate(r.due_at)}</span>}
              </button>
              {open === r.id && (
                <div className="mt-3 space-y-3">
                  {r.overdue && <Alert kind="warn">{t("req.overdueHint")}</Alert>}
                  <Textarea defaultValue={r.body} rows={12} className="font-mono text-xs" onBlur={(e) => e.target.value !== r.body && set(r.id, { body: e.target.value })} aria-label="Text" />
                  <div className="flex flex-wrap gap-2">
                    <a href={r.mailto} className={buttonVariants({ size: "sm" })}><Mail className="h-4 w-4" />{t("req.mailto")}</a>
                    <Button size="sm" variant="outline" onClick={async () => { await navigator.clipboard.writeText(r.body); setCopied(r.id); }}><Copy className="h-4 w-4" />{copied === r.id ? t("common.copied") : t("common.copy")}</Button>
                    <Button size="sm" variant="outline" onClick={() => download(`/requests/${r.id}/pdf`, `anfrage-${r.kind}.pdf`)}><FileDown className="h-4 w-4" />{t("req.pdf")}</Button>
                  </div>
                  <div className="flex flex-wrap gap-2 border-t pt-3">
                    {r.status === "open" && <Button size="sm" onClick={() => set(r.id, { status: "sent" })}>{t("req.markSent")}</Button>}
                    {r.status === "sent" && <><Button size="sm" variant="accent" onClick={() => set(r.id, { status: "done" })}>{t("req.markDone")}</Button>
                      <Button size="sm" variant="outline" onClick={() => set(r.id, { status: "rejected" })}>{t("req.markRejected")}</Button></>}
                    <Button size="sm" variant="ghost" onClick={async () => { if (confirm(`${t("common.delete")}?`)) { await api(`/requests/${r.id}`, { method: "DELETE" }); reload(); } }}>{t("common.delete")}</Button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
export default function Page() { return <Suspense><Requests /></Suspense>; }
