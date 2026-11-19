"use client";
// Week view of the timetable (+ Moodle dates), deadlines with calendar export.
import { CalendarPlus, ChevronLeft, ChevronRight, Mic } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { useApp } from "@/components/providers";
import { Badge, Button, Card, CardTitle, cn, Input, Label, ModuleChip, Select, Sheet } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime, fmtTime, relDays } from "@/lib/format";
import type { Deadline, Module } from "@/lib/types";

interface Ev { id: number; title: string; start: string; end: string; location: string; module_id: number | null; module: string | null; color: string | null; source: string }

function monday(d: Date) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
}
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T00:00:00`;

export default function CalendarPage() {
  const { toast } = useApp();
  const [week, setWeek] = useState(monday(new Date()));
  const [events, setEvents] = useState<Ev[]>([]);
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [mods, setMods] = useState<Module[]>([]);
  const [add, setAdd] = useState(false);
  const [f, setF] = useState({ title: "", due: "", module_id: "" });

  const load = useCallback(() => {
    api.get<Ev[]>(`/events?start=${iso(week)}&days=7`).then(setEvents);
    api.get<Deadline[]>("/deadlines").then(setDeadlines);
  }, [week]);
  useEffect(() => {
    load();
    api.get<Module[]>("/modules").then(setMods);
  }, [load]);

  const days = Array.from({ length: 7 }, (_, i) => new Date(week.getTime() + i * 86400000));
  const today = new Date().toDateString();
  const setStatus = async (d: Deadline, status: string) => {
    await api.patch(`/deadlines/${d.id}`, { status });
    load();
  };
  const create = async () => {
    await api.post("/deadlines", { title: f.title, due: f.due, module_id: f.module_id ? Number(f.module_id) : null });
    setAdd(false);
    setF({ title: "", due: "", module_id: "" });
    toast("Frist angelegt", "ok");
    load();
  };

  return (
    <>
      <PageHeader title="Kalender" subtitle={`Woche ab ${week.toLocaleDateString("de-DE", { day: "numeric", month: "long" })}`} action={
        <div className="flex gap-1">
          <Button variant="outline" size="icon" onClick={() => setWeek(new Date(week.getTime() - 7 * 86400000))} aria-label="Vorige Woche"><ChevronLeft className="h-5 w-5" /></Button>
          <Button variant="outline" onClick={() => setWeek(monday(new Date()))}>Heute</Button>
          <Button variant="outline" size="icon" onClick={() => setWeek(new Date(week.getTime() + 7 * 86400000))} aria-label="Nächste Woche"><ChevronRight className="h-5 w-5" /></Button>
        </div>
      } />
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {days.map((d) => {
            const evs = events.filter((e) => new Date(e.start).toDateString() === d.toDateString());
            return (
              <Card key={d.toISOString()} className={cn("p-3", d.toDateString() === today && "border-primary")}>
                <p className={cn("mb-2 text-sm font-semibold", d.toDateString() === today && "text-primary")}>{d.toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "numeric" })}</p>
                {evs.length === 0 ? <p className="text-sm text-muted">frei</p> : (
                  <ul className="space-y-2">
                    {evs.map((e) => (
                      <li key={e.id} className="rounded-lg border-l-4 bg-surface-2 p-2 text-sm" style={{ borderColor: e.color || "var(--border)" }}>
                        <p className="tabular-nums text-xs text-muted">{fmtTime(e.start)}–{fmtTime(e.end)} {e.location && `· ${e.location}`}</p>
                        <p className="font-medium leading-tight">{e.title}</p>
                        <div className="mt-1 flex items-center gap-2">
                          {e.module ? <ModuleChip short={e.module} color={e.color} /> : <Link href="/inbox?tab=review" className="text-xs text-pruefen">kein Modul</Link>}
                          {e.source === "moodle" && <Badge>Moodle</Badge>}
                          {e.module_id && new Date(e.end) > new Date() && new Date(e.start).toDateString() === today && <Link href="/live" className="ml-auto text-primary" aria-label="Live starten"><Mic className="h-4 w-4" /></Link>}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            );
          })}
        </div>
        <Card>
          <CardTitle action={<Button size="sm" variant="outline" onClick={() => setAdd(true)}>+ Frist</Button>}>Fristen</CardTitle>
          <ul className="space-y-3">
            {deadlines.map((d) => (
              <li key={d.id} className="text-sm">
                <p className="font-medium">{d.title} {d.status === "proposed" && <Badge color="var(--pruefen)">Vorschlag</Badge>}</p>
                <p className="text-muted">{relDays(d.due)} · {fmtDateTime(d.due)} · {d.source === "moodle" ? "Moodle" : d.source === "document" ? "aus Dokument" : "manuell"}</p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {d.status === "proposed" && <Button size="sm" onClick={() => setStatus(d, "accepted")}>Übernehmen</Button>}
                  <a href={`/api/deadlines/${d.id}/ics`}><Button size="sm" variant="outline"><CalendarPlus className="h-4 w-4" /> In Kalender</Button></a>
                  <Button size="sm" variant="ghost" onClick={() => setStatus(d, d.status === "proposed" ? "dismissed" : "done")}>{d.status === "proposed" ? "Verwerfen" : "Erledigt"}</Button>
                </div>
              </li>
            ))}
            {deadlines.length === 0 && <p className="text-muted">Keine Fristen.</p>}
          </ul>
        </Card>
      </div>
      <Sheet open={add} onClose={() => setAdd(false)} title="Neue Frist">
        <div className="space-y-3">
          <div><Label>Titel</Label><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></div>
          <div><Label>Fällig</Label><Input type="datetime-local" value={f.due} onChange={(e) => setF({ ...f, due: e.target.value })} /></div>
          <div><Label>Modul</Label><Select value={f.module_id} onChange={(e) => setF({ ...f, module_id: e.target.value })}><option value="">–</option>{mods.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</Select></div>
          <Button className="w-full" disabled={!f.title || !f.due} onClick={create}>Anlegen</Button>
        </div>
      </Sheet>
    </>
  );
}
