"use client";
// First-launch wizard: max 6 steps, progress bar, skippable and resumable (step is stored server-side).
import { Check, ChevronLeft, ChevronRight, Fingerprint, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CalendarConnect, KeyField, MoodleConnect, UploadZone, type SecretInfo } from "@/components/connect";
import { useApp } from "@/components/providers";
import { Button, Card, Input, Notice, Progress, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { passkeySupported, registerPasskey } from "@/lib/passkey";
import type { Module, User } from "@/lib/types";

const STEPS = ["Konto", "API-Keys", "Stundenplan", "Moodle", "Module", "Import"];

export default function SetupPage() {
  const { reloadUser, toast } = useApp();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [step, setStep] = useState(1);
  const [secrets, setSecrets] = useState<SecretInfo[]>([]);
  const [modules, setModules] = useState<Module[]>([]);
  const [suggest, setSuggest] = useState<{ name: string; count: number; lecturer: string }[]>([]);
  const [newName, setNewName] = useState("");

  const loadSecrets = useCallback(() => api.get<SecretInfo[]>("/secrets").then(setSecrets), []);
  const loadModules = useCallback(() => {
    api.get<Module[]>("/modules").then(setModules);
    api.get<typeof suggest>("/modules-suggestions").then(setSuggest);
  }, []);

  useEffect(() => {
    reloadUser().then((u) => {
      if (!u) return router.replace("/login");
      setUser(u);
      setStep(Math.min(6, Math.max(1, u.setup_step)));
    });
    loadSecrets();
    loadModules();
  }, [reloadUser, router, loadSecrets, loadModules]);

  if (!user) return <Spinner />;

  const go = async (next: number, skipped = false) => {
    if (next > step || skipped) await api.post("/setup/step", { step, skipped });
    if (next > 6) {
      await api.post("/setup/step", { step: 6, skipped });
      await reloadUser();
      router.replace("/");
      return;
    }
    setStep(next);
    if (next === 5) loadModules();
  };

  const addModule = async (name: string, lecturer = "") => {
    await api.post("/modules", { name, lecturer });
    toast(`Modul „${name}“ angelegt`, "ok");
    setNewName("");
    loadModules();
  };

  return (
    <main className="safe-top mx-auto max-w-3xl p-4 pb-24">
      <div className="mb-6 flex items-center gap-3">
        <img src="/logo.svg" alt="" className="h-10 w-10" />
        <div className="flex-1">
          <p className="text-sm text-muted">Einrichtung · Schritt {step} von 6</p>
          <h1 className="text-xl font-bold">{STEPS[step - 1]}</h1>
        </div>
      </div>
      <Progress value={step / 6} className="mb-2" />
      <ol className="mb-6 flex justify-between text-xs text-muted">
        {STEPS.map((s, i) => (
          <li key={s} className={i + 1 === step ? "font-semibold text-primary" : ""}>
            {i + 1 < step ? <Check className="mx-auto h-3.5 w-3.5" /> : null}
            <span className="hidden sm:inline">{s}</span>
          </li>
        ))}
      </ol>

      {step === 1 && (
        <Card className="space-y-3">
          <p>Dein Konto <b>{user.email}</b> ist angelegt. Das Passwort ist mit Argon2id geschützt.</p>
          {passkeySupported() && (
            <Button variant="outline" onClick={() => registerPasskey().then(() => toast("Passkey gespeichert", "ok")).catch((e) => toast((e as Error).message, "error"))}>
              <Fingerprint className="h-5 w-5" /> Optional: Face ID / Passkey einrichten
            </Button>
          )}
        </Card>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <Notice>Beide Keys sind kostenlos erhältlich. Ohne Keys funktioniert der Rest der App – die betroffenen Funktionen zeigen dann, was fehlt.</Notice>
          <KeyField provider="groq" info={secrets.find((s) => s.provider === "groq")} onChange={loadSecrets} />
          <KeyField provider="gemini" info={secrets.find((s) => s.provider === "gemini")} onChange={loadSecrets} />
        </div>
      )}

      {step === 3 && (
        <Card><CalendarConnect onAdded={loadModules} /></Card>
      )}

      {step === 4 && (
        <Card><MoodleConnect /></Card>
      )}

      {step === 5 && (
        <Card className="space-y-4">
          {suggest.length > 0 && (
            <div>
              <p className="mb-2 font-medium">Aus deinem Stundenplan erkannt:</p>
              <div className="flex flex-wrap gap-2">
                {suggest.filter((s) => !modules.some((m) => m.name === s.name)).map((s) => (
                  <Button key={s.name} variant="outline" size="sm" onClick={() => addModule(s.name, s.lecturer)}>
                    <Plus className="h-4 w-4" /> {s.name} <span className="text-muted">({s.count}×)</span>
                  </Button>
                ))}
              </div>
            </div>
          )}
          <div>
            <p className="mb-2 font-medium">Deine Module ({modules.length})</p>
            <ul className="mb-3 space-y-1">
              {modules.map((m) => (
                <li key={m.id} className="flex items-center gap-2"><span className="h-3 w-3 rounded-full" style={{ background: m.color }} />{m.name}</li>
              ))}
            </ul>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (newName.trim()) addModule(newName.trim()); }}>
              <Input placeholder="z. B. Grundlagen des Steuerrechts" value={newName} onChange={(e) => setNewName(e.target.value)} />
              <Button type="submit" disabled={!newName.trim()}>Hinzufügen</Button>
            </form>
            <div className="mt-3 flex flex-wrap gap-2 text-sm">
              {["Einstieg in die Steuerberatung", "Grundlagen BWL", "Grundlagen des Steuerrechts", "Grundlagen im Schuld- und Sachenrecht", "Buchführung"]
                .filter((n) => !modules.some((m) => m.name === n))
                .map((n) => (
                  <button key={n} className="rounded-full border border-border px-3 py-1.5 hover:bg-surface-2" onClick={() => addModule(n)}>+ {n}</button>
                ))}
            </div>
          </div>
        </Card>
      )}

      {step === 6 && (
        <Card className="space-y-3">
          <p>Alte Sprachmemos und Dateien importieren: Lernzentrum ordnet sie anhand von Datum und Stundenplan dem richtigen Modul und der richtigen Vorlesung zu. Unsichere Fälle landen in der Prüfliste.</p>
          <UploadZone channel="import" label="Sprachmemos & Dateien hierher ziehen" />
        </Card>
      )}

      <div className="safe-bottom fixed inset-x-0 bottom-0 border-t border-border bg-surface/95 p-3 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-2">
          <Button variant="ghost" onClick={() => setStep(Math.max(1, step - 1))} disabled={step === 1}><ChevronLeft className="h-4 w-4" /> Zurück</Button>
          <div className="flex-1" />
          {step > 1 && <Button variant="outline" onClick={() => go(step + 1, true)}>Überspringen</Button>}
          <Button onClick={() => go(step + 1)}>{step === 6 ? "Fertig" : "Weiter"} <ChevronRight className="h-4 w-4" /></Button>
        </div>
      </div>
    </main>
  );
}
