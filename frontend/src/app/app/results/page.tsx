"use client";
import { useMemo, useState } from "react";
import { FileSearch } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Empty, Skeleton } from "@/components/ui/misc";
import { FindingRow, RequestLink, type Finding } from "@/components/app/finding";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

export default function Results() {
  const { t } = useT();
  const [q, setQ] = useState("");
  const [module, setModule] = useState("");
  const [risk, setRisk] = useState("");
  const [status, setStatus] = useState("active");
  const qs = useMemo(() => new URLSearchParams(Object.entries({ q, module, risk, status }).filter(([, v]) => v)).toString(), [q, module, risk, status]);
  const { data, reload, loading } = useApi<{ items: Finding[]; total: number }>(`/findings?${qs}`);
  const patch = async (id: string, body: any) => { await api(`/findings/${id}`, { method: "PATCH", body }); reload(); };
  const tagPrompt = async (f: Finding) => {
    const v = prompt(`${t("results.tags")} (Komma-getrennt)`, f.tags.join(", "));
    if (v !== null) await patch(f.id, { tags: v.split(",").map((s) => s.trim()).filter(Boolean) });
  };
  const notePrompt = async (f: Finding) => {
    const v = prompt(t("results.note"), f.note ?? "");
    if (v !== null) await patch(f.id, { note: v });
  };
  const top = data?.items.find((f) => f.status === "open" && f.risk === "high");
  return (
    <div>
      <PageHeader title={t("results.title")} explain={t("results.explain")}
        next={top ? { label: `${t("results.request")}: ${top.title.slice(0, 40)}`, href: `/app/requests/new?finding=${top.id}` } : { label: t("scan.basic"), href: "/app/scan" }} />
      <div className="mb-4 grid gap-2 sm:grid-cols-4">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("common.search")} aria-label={t("common.search")} />
        <Select value={module} onChange={(e) => setModule(e.target.value)} aria-label="Modul">
          <option value="">{t("common.all")}</option><option value="privacy_scan">{t("nav.scan")}</option><option value="breach_check">{t("nav.breaches")}</option>
        </Select>
        <Select value={risk} onChange={(e) => setRisk(e.target.value)} aria-label={t("common.risk")}>
          <option value="">{t("common.risk")}: {t("common.all")}</option>{["high", "medium", "low"].map((r) => <option key={r} value={r}>{t(`risk.${r}`)}</option>)}
        </Select>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="active">{t("common.open_status")} + {t("common.done")}</option><option value="open">{t("common.open_status")}</option>
          <option value="done">{t("common.done")}</option><option value="trash">{t("results.trash")}</option>
        </Select>
      </div>
      {status === "trash" && !!data?.total && <Button variant="outline" size="sm" className="mb-3" onClick={async () => { await api("/findings/trash", { method: "DELETE" }); reload(); }}>{t("results.emptyTrash")}</Button>}
      {loading && !data ? <Skeleton className="h-40" /> : !data?.items.length ? <Empty icon={<FileSearch className="h-8 w-8" />} title={t("results.empty")} /> : (
        <ul className="space-y-3">
          {data.items.map((f) => (
            <FindingRow key={f.id} f={f} actions={<>
              {f.status !== "trash" && <RequestLink f={f} />}
              {f.status === "open" && <Button size="sm" variant="outline" onClick={() => patch(f.id, { status: "done" })}>{t("results.markDone")}</Button>}
              {f.status !== "trash" ? <Button size="sm" variant="ghost" onClick={() => patch(f.id, { status: "trash" })}>{t("results.trash")}</Button>
                : <Button size="sm" variant="outline" onClick={() => patch(f.id, { status: "open" })}>{t("results.restore")}</Button>}
              <Button size="sm" variant="ghost" onClick={() => tagPrompt(f)}>{t("results.tags")}{f.tags.length ? ` (${f.tags.join(", ")})` : ""}</Button>
              <Button size="sm" variant="ghost" onClick={() => notePrompt(f)}>{t("results.note")}{f.note ? " ✓" : ""}</Button>
            </>} />
          ))}
        </ul>
      )}
    </div>
  );
}
