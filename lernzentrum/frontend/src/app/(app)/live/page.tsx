"use client";
// Live mode entry: one-tap start for the lecture running now, module picker, past recordings.
import { Mic, PlayCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { StartLive } from "@/components/start-live";
import { Badge, Button, Card, CardTitle, Empty, ModuleChip, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime, fmtDuration, fmtTime } from "@/lib/format";
import type { Module, Recording } from "@/lib/types";

export default function LiveIndex() {
  const [current, setCurrent] = useState<{ lecture_id: number; module_id: number; module: string; start: string; end: string } | null | undefined>(undefined);
  const [modules, setModules] = useState<Module[]>([]);
  const [recs, setRecs] = useState<Recording[]>([]);
  const [open, setOpen] = useState<{ module_id?: number; lecture_id?: number } | null>(null);

  useEffect(() => {
    api.get<{ current: typeof current }>("/lectures/current").then((r) => setCurrent(r.current));
    api.get<Module[]>("/modules").then(setModules);
    api.get<Recording[]>("/recordings").then(setRecs);
  }, []);
  if (current === undefined) return <Spinner />;

  return (
    <>
      <PageHeader title="Live-Modus" subtitle="Zuhören, transkribieren, Fragen erkennen – Antworten nur als Text." />
      <Card className="mb-5 flex flex-col items-center gap-4 py-8 text-center">
        {current ? (
          <>
            <p className="text-muted">Laut Stundenplan läuft gerade ({fmtTime(current.start)}–{fmtTime(current.end)}):</p>
            <p className="text-2xl font-semibold">{current.module}</p>
            <button
              onClick={() => setOpen({ module_id: current.module_id, lecture_id: current.lecture_id })}
              className="rec-pulse flex h-28 w-28 items-center justify-center rounded-full bg-unsicher text-white shadow-lg"
              aria-label={`Aufnahme für ${current.module} starten`}
            >
              <Mic className="h-12 w-12" />
            </button>
            <Button variant="ghost" onClick={() => setOpen({})}>Anderes Modul wählen</Button>
          </>
        ) : (
          <>
            <p className="text-muted">Gerade läuft keine Vorlesung laut Stundenplan.</p>
            <button onClick={() => setOpen({})} className="flex h-28 w-28 items-center justify-center rounded-full bg-primary text-primary-fg shadow-lg" aria-label="Aufnahme starten">
              <Mic className="h-12 w-12" />
            </button>
            <p className="text-sm text-muted">Modul im nächsten Schritt wählen</p>
          </>
        )}
      </Card>
      <Card>
        <CardTitle>Aufnahmen</CardTitle>
        {recs.length === 0 ? (
          <Empty icon={<PlayCircle />} title="Noch keine Aufnahmen" />
        ) : (
          <ul className="divide-y divide-border">
            {recs.map((r) => (
              <li key={r.id}>
                <Link href={`/live/${r.id}`} className="flex items-center gap-3 py-3">
                  <ModuleChip short={r.module_short} color={r.color} />
                  <span className="flex-1 truncate font-medium">{r.title}</span>
                  <span className="hidden text-sm text-muted sm:inline">{fmtDateTime(r.started_at)}</span>
                  <span className="text-sm tabular-nums text-muted">{fmtDuration(r.duration_s)}</span>
                  {r.status === "live" && <Badge color="var(--unsicher)">live</Badge>}
                  {r.source === "import" && <Badge>Import</Badge>}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <StartLive open={!!open} onClose={() => setOpen(null)} initial={open || {}} modules={modules} />
    </>
  );
}
