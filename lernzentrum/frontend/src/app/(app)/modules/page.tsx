"use client";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { useApp } from "@/components/providers";
import { Button, Card, Empty, Input, Label, Sheet, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Module } from "@/lib/types";

export default function ModulesPage() {
  const { toast } = useApp();
  const [mods, setMods] = useState<Module[] | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", short: "", lecturer: "", exam_date: "" });
  const load = () => api.get<Module[]>("/modules").then(setMods);
  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    try {
      await api.post("/modules", { name: form.name, short: form.short || undefined, lecturer: form.lecturer, exam_date: form.exam_date ? `${form.exam_date}T09:00:00` : null });
      setOpen(false);
      setForm({ name: "", short: "", lecturer: "", exam_date: "" });
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  if (!mods) return <Spinner />;
  return (
    <>
      <PageHeader title="Module" subtitle="Jedes Modul hat eigene Materialien, Aufnahmen, Karten und einen Dozenten-Steckbrief." action={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Modul</Button>} />
      {mods.length === 0 ? (
        <Empty title="Noch keine Module">Lege Module an oder lass sie aus deinem Stundenplan erkennen (Einstellungen → Kalender).</Empty>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {mods.filter((m) => !m.archived).map((m) => (
            <Link key={m.id} href={`/modules/${m.id}`}>
              <Card className="h-full hover:bg-surface-2">
                <div className="mb-2 flex items-center gap-2">
                  <span className="rounded-md px-2 py-0.5 text-sm font-bold text-white" style={{ background: m.color }}>{m.short}</span>
                  {m.exam_mode && <span className="text-xs font-semibold text-pruefen">Prüfungsmodus</span>}
                </div>
                <p className="font-semibold">{m.name}</p>
                <p className="text-sm text-muted">{m.lecturer || "Dozent unbekannt"}</p>
                {m.exam_date && <p className="mt-2 text-sm">Prüfung: {fmtDate(m.exam_date)}</p>}
              </Card>
            </Link>
          ))}
        </div>
      )}
      <Sheet open={open} onClose={() => setOpen(false)} title="Neues Modul">
        <div className="space-y-3">
          <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Grundlagen des Steuerrechts" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label hint="optional">Kürzel</Label><Input value={form.short} onChange={(e) => setForm({ ...form, short: e.target.value })} placeholder="GStR" /></div>
            <div><Label hint="optional">Prüfungstermin</Label><Input type="date" value={form.exam_date} onChange={(e) => setForm({ ...form, exam_date: e.target.value })} /></div>
          </div>
          <div><Label hint="optional">Dozent/in</Label><Input value={form.lecturer} onChange={(e) => setForm({ ...form, lecturer: e.target.value })} /></div>
          <Button className="w-full" onClick={create} disabled={!form.name.trim()}>Anlegen</Button>
        </div>
      </Sheet>
    </>
  );
}
