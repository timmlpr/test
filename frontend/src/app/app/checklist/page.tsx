"use client";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Progress, Tabs } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { security } from "@/content/checklists";

export default function Checklist() {
  const { t } = useT();
  const { data, setData } = useApi<any>("/checklist");
  const [os, setOs] = useState<Record<string, string>>({});
  const toggle = async (item: string, done: boolean) => setData(await api("/checklist", { method: "PATCH", body: { item, done } }));
  const state = Object.fromEntries((data?.items ?? []).map((i: any) => [i.key, i.done]));
  const next = security.find((i) => !state[i.key]);
  return (
    <div>
      <PageHeader title={t("check.title")} explain={t("check.explain")} next={next ? { label: next.title, href: `#${next.key}` } : undefined} />
      {data && <div className="mb-6 space-y-1"><p className="text-sm">{t("check.progress", { done: data.done, total: data.total })}</p><Progress value={(data.done / data.total) * 100} label="Fortschritt" /></div>}
      <ul className="space-y-3">
        {security.map((it) => {
          const tabs = Object.keys(it.steps);
          const cur = os[it.key] ?? tabs[0];
          return (
            <li key={it.key} id={it.key}>
              <Card className={state[it.key] ? "border-ok/40" : ""}>
                <details className="group p-4" open={next?.key === it.key}>
                  <summary className="flex cursor-pointer list-none items-start gap-3">
                    <input type="checkbox" className="mt-1 h-5 w-5 accent-[hsl(var(--accent))]" checked={!!state[it.key]} onChange={(e) => toggle(it.key, e.target.checked)}
                      onClick={(e) => e.stopPropagation()} aria-label={`${it.title} erledigt`} />
                    <span><span className={state[it.key] ? "font-medium line-through opacity-70" : "font-medium"}>{it.title}</span><span className="block text-sm text-muted-foreground">{it.why}</span></span>
                  </summary>
                  <div className="mt-3 space-y-3 pl-8">
                    {tabs.length > 1 && <Tabs tabs={tabs.map((x) => ({ id: x, label: x }))} value={cur} onChange={(v) => setOs({ ...os, [it.key]: v })} />}
                    <ol className="list-decimal space-y-1 pl-5 text-sm">{it.steps[cur].map((s) => <li key={s}>{s}</li>)}</ol>
                  </div>
                </details>
              </Card>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
