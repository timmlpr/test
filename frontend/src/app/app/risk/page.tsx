"use client";
import Link from "next/link";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, Skeleton } from "@/components/ui/misc";
import { RiskGauge } from "@/components/risk-gauge";
import { useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

export default function Risk() {
  const { t } = useT();
  const risk = useApi<any>("/risk");
  const hist = useApi<any[]>("/risk/history");
  if (!risk.data) return <Skeleton className="h-64" />;
  const r = risk.data;
  const top = r.actions.find((a: any) => a.impact > 0);
  const series = (hist.data ?? []).map((h) => ({ at: fmtDate(h.at), score: h.score }));
  return (
    <div className="space-y-6">
      <PageHeader title={t("risk.title")} explain={t("risk.explain")}
        next={top ? { label: top.finding_id ? `${t("results.request")}: ${top.title.slice(0, 40)}` : t("next.checklist"), href: top.finding_id ? `/app/requests/new?finding=${top.finding_id}` : "/app/checklist" } : undefined} />
      <div className="grid gap-4 lg:grid-cols-[auto_1fr]">
        <Card className="flex items-center justify-center p-6"><RiskGauge score={r.score} light={r.light} /></Card>
        <Card>
          <CardHeader><CardTitle className="text-base">{t("risk.factors")}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {Object.entries(r.factors).map(([k, v]: any) => (
              <div key={k}>
                <div className="flex justify-between text-sm"><span>{t(`factor.${k}`)}</span><span className="font-mono">{v > 0 ? `+${v}` : v} / {k === "protection" ? "−" : ""}{r.caps[k]}</span></div>
                <Progress value={(Math.abs(v) / r.caps[k]) * 100} label={t(`factor.${k}`)} />
                <p className="mt-0.5 text-xs text-muted-foreground">{t(`factor.${k}.d`)}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-base">{t("risk.history")}</CardTitle></CardHeader>
        <CardContent className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ left: -20, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="at" tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
              <Line type="monotone" dataKey="score" name={t("home.score")} stroke="hsl(var(--primary))" strokeWidth={2.5} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">{t("risk.actions")}</CardTitle></CardHeader>
        <CardContent>
          <ol className="space-y-2">
            {r.actions.filter((a: any) => a.impact > 0).map((a: any, i: number) => (
              <li key={i} className="flex items-center justify-between gap-2 rounded-md border p-3 text-sm">
                <Link href={a.finding_id ? `/app/requests/new?finding=${a.finding_id}` : "/app/checklist"} className="truncate hover:text-primary">
                  {i + 1}. {a.title === "checklist_next" ? t("next.checklist") : a.title}</Link>
                <span className="shrink-0 font-semibold text-accent">{t("risk.impact", { n: a.impact })}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
