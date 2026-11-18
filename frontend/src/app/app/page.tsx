"use client";
import Link from "next/link";
import { ArrowRight, CalendarClock, FileSearch, KeyRound, Radar, Shield } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/misc";
import { RiskGauge } from "@/components/risk-gauge";
import { ErrorNotice } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

export default function Home() {
  const { t } = useT();
  const { user } = useAuth();
  const { data, error } = useApi<any>("/home");
  if (error) return <ErrorNotice error={error} />;
  if (!data) return <div className="space-y-4"><Skeleton className="h-48" /><Skeleton className="h-24" /></div>;
  const ns = data.next_step;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold sm:text-3xl">{t("home.title")}{user?.display_name ? `, ${user.display_name.split(" ")[0]}` : ""}</h1>
        <p className="mt-1 text-muted-foreground">{t("home.explain")}</p>
      </header>
      <div className="grid gap-4 lg:grid-cols-[auto_1fr]">
        <Card className="flex flex-col items-center justify-center p-6">
          <RiskGauge score={data.risk.score} light={data.risk.light} />
          <p className="mt-3 text-xs text-muted-foreground">{t("home.scoreHint")}</p>
          <div className="mt-3 flex gap-2 text-sm">
            <Badge variant="muted">{data.counts.open} {t("home.open")}</Badge><Badge variant="bad">{data.counts.high} {t("home.high")}</Badge>
          </div>
          <Link href="/app/risk" className="mt-2 text-sm text-primary underline">Wie entsteht der Wert?</Link>
        </Card>
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader><span className="text-xs font-semibold uppercase tracking-wide text-primary">{t("common.nextStep")}</span>
            <CardTitle className="text-xl">{t(`next.${ns.key}`, { finding: ns.finding ?? "" })}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {ns.impact ? <p className="text-sm text-muted-foreground">Senkt deinen Risiko-Wert um etwa {ns.impact} Punkte.</p> : null}
            <Link href={ns.href} className={buttonVariants({ size: "lg" })}>{t("next.go")}<ArrowRight className="h-4 w-4" /></Link>
          </CardContent>
        </Card>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><CalendarClock className="h-4 w-4" />{t("home.deadlines")}</CardTitle></CardHeader>
          <CardContent>
            {data.deadlines.length === 0 ? <p className="text-sm text-muted-foreground">{t("home.noDeadlines")}</p> : (
              <ul className="space-y-2">{data.deadlines.map((d: any) => (
                <li key={d.id} className="flex items-center justify-between gap-2 text-sm">
                  <Link href={`/app/requests?id=${d.id}`} className="truncate hover:text-primary">{d.recipient}</Link>
                  {d.overdue ? <Badge variant="bad">{t("home.overdue")}</Badge> : <span className="text-muted-foreground">{fmtDate(d.due_at)}</span>}
                </li>))}
              </ul>)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><FileSearch className="h-4 w-4" />{t("home.newFindings")}</CardTitle></CardHeader>
          <CardContent>
            {data.new_findings.length === 0 ? <p className="text-sm text-muted-foreground">{t("home.noNew")}</p> : (
              <ul className="space-y-2">{data.new_findings.map((f: any) => (
                <li key={f.id} className="flex items-center gap-2 text-sm"><RiskBadge risk={f.risk} label={t(`risk.${f.risk}`)} />
                  <Link href={`/app/results#${f.id}`} className="truncate hover:text-primary">{f.title}</Link></li>))}
              </ul>)}
          </CardContent>
        </Card>
      </div>
      <section aria-labelledby="quick">
        <h2 id="quick" className="mb-3 font-semibold">{t("home.quick")}</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[["/app/scan", Radar, "nav.scan"], ["/app/scam", Shield, "nav.scam"], ["/app/passwords", KeyRound, "nav.passwords"], ["/app/requests", CalendarClock, "nav.requests"]].map(([href, Icon, k]: any) => (
            <Link key={href} href={href} className="flex flex-col items-center gap-2 rounded-lg border bg-card p-4 text-center text-sm hover:border-primary">
              <Icon className="h-6 w-6 text-primary" />{t(k)}
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
