"use client";
// Consent reminder + module picker before every recording. Consent is logged server-side with a timestamp.
import { Mic, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Module, Recording } from "@/lib/types";
import { useApp } from "./providers";
import { Button, Label, Notice, Select, Sheet } from "./ui";

export function StartLive({ open, onClose, initial, modules }: { open: boolean; onClose: () => void; initial: { module_id?: number; lecture_id?: number }; modules: Module[] }) {
  const { user, toast } = useApp();
  const router = useRouter();
  const [moduleId, setModuleId] = useState<number | "">("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<{ text: string; info: string } | null>(null);
  const reminder = user?.settings.consent_reminder !== false;

  useEffect(() => {
    if (open) {
      setModuleId(initial.module_id ?? "");
      setConsent(false);
      api.get<{ text: string; info: string }>("/consent-text").then(setInfo).catch(() => undefined);
    }
  }, [open, initial.module_id]);

  const mod = modules.find((m) => m.id === moduleId);

  const start = async () => {
    setBusy(true);
    try {
      const rec = await api.post<Recording>("/recordings/start", {
        module_id: moduleId || null,
        lecture_id: initial.module_id === moduleId ? initial.lecture_id ?? null : null,
        consent,
      });
      router.push(`/live/${rec.id}?autostart=1`);
    } catch (e) {
      toast((e as Error).message, "error");
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title="Live-Modus starten">
      <div className="space-y-4">
        <div>
          <Label>Modul</Label>
          <Select value={moduleId} onChange={(e) => setModuleId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Ohne Modul</option>
            {modules.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </Select>
        </div>
        {mod?.exam_mode && (
          <Notice tone="warn">Prüfungsmodus ist für dieses Modul aktiv: Es werden keine Live-Antworten angezeigt. Die App darf in Prüfungen nicht verwendet werden.</Notice>
        )}
        {reminder && (
          <div className="rounded-xl border border-border bg-surface-2 p-3">
            <p className="mb-2 flex items-center gap-2 font-semibold">
              <ShieldCheck className="h-5 w-5 text-primary" /> Einwilligung
            </p>
            <p className="mb-2 text-sm text-muted">{info?.info}</p>
            <label className="flex min-h-11 cursor-pointer items-start gap-3">
              <input type="checkbox" className="mt-1 h-5 w-5 accent-[var(--primary)]" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span className="text-sm">{info?.text || "Alle Anwesenden haben der Aufnahme zugestimmt."}</span>
            </label>
          </div>
        )}
        <Notice>Halte die App im Vordergrund: iPad-Browser nehmen im Hintergrund nicht auf. Der Bildschirm bleibt während der Aufnahme an.</Notice>
        <Button size="lg" className="w-full" onClick={start} loading={busy} disabled={reminder && !consent}>
          <Mic className="h-5 w-5" /> Aufnahme starten
        </Button>
      </div>
    </Sheet>
  );
}
