"use client";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Progress, Tabs } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { social, socialLabels } from "@/content/checklists";

export default function Social() {
  const { t } = useT();
  const { data, setData } = useApi<any>("/social");
  const [p, setP] = useState("instagram");
  const toggle = async (item: string, done: boolean) => {
    const r = await api("/social", { method: "PATCH", body: { platform: p, item, done } });
    setData({ ...data, [p]: r });
  };
  const cur = data?.[p];
  const next = cur?.items.find((i: any) => !i.done);
  return (
    <div>
      <PageHeader title={t("social.title")} explain={t("social.explain")} next={next ? { label: social[p][next.key].title, href: `#${next.key}` } : undefined} />
      <Tabs tabs={Object.keys(social).map((k) => ({ id: k, label: `${socialLabels[k]}${data ? ` ${data[k].done}/${data[k].total}` : ""}` }))} value={p} onChange={setP} />
      {cur && <div className="my-4"><Progress value={(cur.done / cur.total) * 100} label={socialLabels[p]} /></div>}
      <ul className="space-y-2">
        {cur?.items.map((i: any) => (
          <li key={i.key} id={i.key}>
            <Card><CardContent className="flex items-start gap-3 pt-4">
              <input type="checkbox" checked={i.done} onChange={(e) => toggle(i.key, e.target.checked)} className="mt-1 h-5 w-5 accent-[hsl(var(--accent))]" aria-label={`${social[p][i.key].title} erledigt`} />
              <div><p className={i.done ? "font-medium line-through opacity-70" : "font-medium"}>{social[p][i.key].title}</p><p className="text-sm text-muted-foreground">{social[p][i.key].how}</p></div>
            </CardContent></Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
