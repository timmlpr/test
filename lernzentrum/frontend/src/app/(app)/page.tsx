"use client";
// Home: today's lectures with one-tap start, deadlines, modules, inbox review, study plan.
import { AlertCircle, ArrowRight, Bell, CalendarClock, Inbox, Layers, Mic, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { LevelBadge } from "@/components/answer-card";
import { useApp } from "@/components/providers";
import { StartLive } from "@/components/start-live";
import { Badge, Button, Card, CardTitle, Empty, ModuleChip, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime, fmtTime, relDays } from "@/lib/format";
import type { Deadline, Level, Module } from "@/lib/types";

interface Home {
  greeting: string;
  current: { lecture_id: number; module_id: number; module: string; title: string; start: string; end: string } | null;
  today: { id: number; title: string; start: string; end: string; location: string; module_id: number | null; module: string | null; color: string | null; lecture_id: number | null; running: boolean }[];
  deadlines: Deadline[];
  modules: Module[];
  review_count: number;
  unmatched_events: number;
  due_cards: number;
  plan: { date: string; module: string; color: string; task: string; minutes: number }[];
  recent_answers: { question: string; level: Level; percent: number }[];
  unread_announcements: number;
}

export default function HomePage() {
  const { user } = useApp();
  const [data, setData] = useState<Home | null>(null);
  const [startFor, setStartFor] = useState<{ module_id?: number; lecture_id?: number } | null>(null);

  useEffect(() => {
    api.get<Home>("/home").then(setData).catch(() => undefined);
  }, []);
  if (!data) return <Spinner />;
  const hour = new Date().getHours();
  const hello = hour < 11 ? "Guten Morgen" : hour < 18 ? "Hallo" : "Guten Abend";
  const mods = Object.fromEntries(data.modules.map((m) => [m.id, m]));

  return (
    <>
      <PageHeader
        title={`${hello}${user?.display_name ? `, ${user.display_name}` : ""}`}
        subtitle={new Date().toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" })}
      />

      {data.current ? (
        <Card className="mb-5 border-2 border-primary/40 bg-primary/5">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-primary">Läuft jetzt · {fmtTime(data.current.start)}–{fmtTime(data.current.end)}</p>
              <p className="text-xl font-semibold">{data.current.module}</p>
            </div>
            <Button size="lg" onClick={() => setStartFor({ lecture_id: data.current!.lecture_id, module_id: data.current!.module_id })}>
              <Mic className="h-5 w-5" /> Aufnahme starten
            </Button>
          </div>
        </Card>
      ) : (
        <Card className="mb-5">
          <div className="flex flex-wrap items-center gap-3">
            <p className="flex-1 text-muted">Gerade läuft laut Stundenplan keine Vorlesung.</p>
            <Button variant="secondary" onClick={() => setStartFor({})}>
              <Mic className="h-5 w-5" /> Live-Modus mit Modulwahl
            </Button>
          </div>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle action={<Link href="/calendar" className="text-sm text-primary">Woche</Link>}>Heute</CardTitle>
          {data.today.length === 0 ? (
            <Empty title="Heute keine Vorlesungen">Genieß den Tag oder arbeite deinen Lernplan ab.</Empty>
          ) : (
            <ul className="divide-y divide-border">
              {data.today.map((e) => (
                <li key={e.id} className="flex items-center gap-3 py-3">
                  <div className="w-24 shrink-0 text-sm tabular-nums text-muted">{fmtTime(e.start)}–{fmtTime(e.end)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <ModuleChip short={e.module} color={e.color} />
                      <span className="truncate font-medium">{e.title}</span>
                      {e.running && <Badge color="var(--unsicher)">läuft</Badge>}
                    </div>
                    <p className="text-sm text-muted">{e.location}</p>
                  </div>
                  {e.module_id ? (
                    <Button size="sm" variant={e.running ? "primary" : "outline"} onClick={() => setStartFor({ lecture_id: e.lecture_id ?? undefined, module_id: e.module_id! })} aria-label={`Aufnahme für ${e.title} starten`}>
                      <Mic className="h-4 w-4" /> Start
                    </Button>
                  ) : (
                    <Link href="/inbox?tab=review" className="text-sm text-pruefen">zuordnen</Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardTitle>Fristen</CardTitle>
          {data.deadlines.length === 0 ? (
            <p className="text-muted">Keine offenen Fristen.</p>
          ) : (
            <ul className="space-y-2">
              {data.deadlines.map((d) => (
                <li key={d.id} className="flex items-start gap-2">
                  <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
                  <div className="min-w-0">
                    <p className="font-medium leading-tight">{d.title}</p>
                    <p className="text-sm text-muted">
                      {relDays(d.due)} · {fmtDateTime(d.due)} {d.module_id && mods[d.module_id] ? `· ${mods[d.module_id].short}` : ""}
                      {d.status === "proposed" && " · Vorschlag"}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="lg:col-span-2">
          <CardTitle action={<Link href="/modules" className="text-sm text-primary">Alle</Link>}>Module</CardTitle>
          <div className="grid gap-3 sm:grid-cols-2">
            {data.modules.map((m) => (
              <Link key={m.id} href={`/modules/${m.id}`} className="flex items-center gap-3 rounded-xl border border-border p-3 hover:bg-surface-2">
                <span className="h-10 w-1.5 rounded-full" style={{ background: m.color }} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{m.name}</p>
                  <p className="text-sm text-muted">
                    {m.due_cards ? `${m.due_cards} Karten fällig` : "Keine Karten fällig"}
                    {m.exam_in_days != null && m.exam_in_days >= 0 ? ` · Prüfung in ${m.exam_in_days} T.` : ""}
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 text-muted" />
              </Link>
            ))}
            {data.modules.length === 0 && <Empty icon={<Layers />} title="Noch keine Module" />}
          </div>
        </Card>

        <div className="space-y-4">
          {(data.review_count > 0 || data.unmatched_events > 0) && (
            <Card className="border-pruefen/50">
              <CardTitle>Bitte bestätigen</CardTitle>
              <p className="mb-3 text-sm text-muted">
                {data.review_count} Datei(en) und {data.unmatched_events} Termin(e) konnten nicht sicher zugeordnet werden.
              </p>
              <Link href="/inbox?tab=review">
                <Button variant="outline" className="w-full"><Inbox className="h-4 w-4" /> Zur Prüfliste</Button>
              </Link>
            </Card>
          )}
          <Card>
            <CardTitle action={<Link href="/learn?tab=plan" className="text-sm text-primary">Plan</Link>}>Als Nächstes lernen</CardTitle>
            {data.due_cards > 0 && (
              <Link href="/learn" className="mb-2 flex items-center gap-2 rounded-xl bg-primary/10 p-3 font-medium text-primary">
                <Sparkles className="h-4 w-4" /> {data.due_cards} Karteikarten wiederholen
              </Link>
            )}
            <ul className="space-y-2">
              {data.plan.map((p, i) => (
                <li key={i} className="flex items-center gap-2 text-sm">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: p.color }} />
                  <span className="flex-1">{p.task}</span>
                  <span className="text-muted">{p.minutes} min</span>
                </li>
              ))}
            </ul>
          </Card>
          {data.unread_announcements > 0 && (
            <Card>
              <Link href="/modules" className="flex items-center gap-2 font-medium">
                <Bell className="h-4 w-4 text-primary" /> {data.unread_announcements} neue Ankündigung(en)
              </Link>
            </Card>
          )}
          {data.recent_answers.length > 0 && (
            <Card>
              <CardTitle action={<Link href="/learn?tab=history" className="text-sm text-primary">Verlauf</Link>}>Letzte Antworten</CardTitle>
              <ul className="space-y-2">
                {data.recent_answers.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <LevelBadge level={a.level} percent={a.percent} />
                    <span className="line-clamp-2">{a.question}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
      {!user?.is_demo && data.modules.length === 0 && (
        <p className="mt-4 flex items-center gap-2 text-sm text-muted"><AlertCircle className="h-4 w-4" /> Lege Module in „Module“ an oder verbinde deinen Stundenplan.</p>
      )}
      <StartLive open={!!startFor} onClose={() => setStartFor(null)} initial={startFor || {}} modules={data.modules} />
    </>
  );
}
