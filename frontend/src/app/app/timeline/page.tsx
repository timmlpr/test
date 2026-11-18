"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Select } from "@/components/ui/input";
import { Empty } from "@/components/ui/misc";
import { useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

const KIND: Record<string, string> = { finding: "Fund", warning: "Warnung", request: "Anfrage", change: "Änderung", scan: "Scan", checklist: "Checkliste" };

export default function Timeline() {
  const { t } = useT();
  const { data } = useApi<any>("/timeline?limit=1000");
  const [kind, setKind] = useState("");
  const [pos, setPos] = useState(100);
  const range = useMemo(() => {
    if (!data?.range?.from) return null;
    const a = new Date(data.range.from + "Z").getTime(), b = new Date(data.range.to + "Z").getTime();
    return { a, b, until: a + ((b - a) * pos) / 100 };
  }, [data, pos]);
  const items = (data?.items ?? []).filter((e: any) => (!kind || e.kind === kind) && (!range || new Date(e.at + "Z").getTime() <= range.until));
  return (
    <div>
      <PageHeader title={t("tl.title")} explain={t("tl.explain")} next={{ label: t("nav.results"), href: "/app/results" }} />
      <div className="mb-6 grid gap-3 sm:grid-cols-[1fr_200px]">
        <label className="text-sm">
          <span className="mb-1 block">{t("tl.until")}: <strong>{range ? new Date(range.until).toLocaleDateString("de-DE") : "–"}</strong></span>
          <input type="range" min={0} max={100} value={pos} onChange={(e) => setPos(+e.target.value)} className="w-full accent-[hsl(var(--primary))]" aria-label="Zeitreise" />
        </label>
        <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Art"><option value="">{t("common.all")}</option>{Object.entries(KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
      </div>
      {!items.length ? <Empty title="Noch keine Ereignisse." /> : (
        <ol className="relative space-y-4 border-l pl-6">
          {items.map((e: any) => (
            <li key={e.id} className="relative">
              <span className="absolute -left-[31px] top-1.5 h-3 w-3 rounded-full border-2 border-background bg-primary" aria-hidden />
              <p className="text-xs text-muted-foreground">{fmtDate(e.at, true)}</p>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <Badge variant="muted">{KIND[e.kind] ?? e.kind}</Badge>{e.risk && <RiskBadge risk={e.risk} label={t(`risk.${e.risk}`)} />}
                {e.kind === "finding" && e.ref ? <Link href={`/app/results#${e.ref}`} className="hover:text-primary">{e.title}</Link> : <span>{e.title}</span>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
