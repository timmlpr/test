"use client";
import { Fingerprint, LogIn } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useApp } from "@/components/providers";
import { Button, Card, Input, Label, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { passkeyLogin } from "@/lib/passkey";
import type { User } from "@/lib/types";

interface Status {
  registration_open: boolean;
  demo: boolean;
  demo_login: { email: string; password: string } | null;
  brand: { name: string; tagline: string };
}

function LoginInner() {
  const router = useRouter();
  const search = useSearchParams();
  const { setUser } = useApp();
  const [status, setStatus] = useState<Status | null>(null);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<Status>("/auth/status").then((s) => {
      setStatus(s);
      if (s.registration_open) setMode("register");
    }).catch(() => setError("Server nicht erreichbar."));
  }, []);

  const done = (u: User) => {
    setUser(u);
    router.replace(u.setup_done ? search.get("next") || "/" : "/setup");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const u = mode === "login"
        ? await api.post<User>("/auth/login", { email, password })
        : await api.post<User>("/auth/register", { email, password, display_name: name });
      done(u);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const demo = async () => {
    if (!status?.demo_login) return;
    setBusy(true);
    try {
      done(await api.post<User>("/auth/login", status.demo_login));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  const withPasskey = async () => {
    setError("");
    try {
      done(await passkeyLogin(email));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <main className="safe-top flex min-h-dvh items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <img src="/logo.svg" alt="" className="h-16 w-16" />
          <h1 className="text-3xl font-bold tracking-tight">{status?.brand.name || "Lernzentrum"}</h1>
          <p className="text-muted">{status?.brand.tagline}</p>
        </div>
        <Card className="p-5">
          <form onSubmit={submit} className="space-y-4">
            <h2 className="text-lg font-semibold">{mode === "login" ? "Anmelden" : "Konto erstellen"}</h2>
            {mode === "register" && (
              <div>
                <Label>Vorname</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" />
              </div>
            )}
            <div>
              <Label>E-Mail</Label>
              <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" inputMode="email" />
            </div>
            <div>
              <Label hint={mode === "register" ? "mind. 10 Zeichen, Groß-/Kleinbuchstaben, Zahl" : undefined}>Passwort</Label>
              <Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            </div>
            {error && <Notice tone="error">{error}</Notice>}
            <Button type="submit" className="w-full" size="lg" loading={busy}>
              <LogIn className="h-5 w-5" /> {mode === "login" ? "Anmelden" : "Konto erstellen"}
            </Button>
            {mode === "login" && (
              <Button type="button" variant="outline" className="w-full" onClick={withPasskey} disabled={!email}>
                <Fingerprint className="h-5 w-5" /> Mit Face ID / Passkey
              </Button>
            )}
          </form>
          {status?.registration_open && (
            <button className="mt-4 w-full text-center text-sm text-primary" onClick={() => setMode(mode === "login" ? "register" : "login")}>
              {mode === "login" ? "Neues Konto erstellen" : "Ich habe schon ein Konto"}
            </button>
          )}
        </Card>
        {status?.demo && (
          <Card className="mt-4 p-5 text-center">
            <p className="mb-3 text-sm text-muted">Ausprobieren ohne Keys: Demo mit Beispielmodulen, Folien, Aufnahme und Antworten.</p>
            <Button variant="secondary" className="w-full" onClick={demo} loading={busy}>Demo öffnen</Button>
          </Card>
        )}
        <p className="mt-6 text-center text-xs text-muted">Private Lern-App · Daten in der EU · Nicht in Prüfungen verwenden</p>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginInner />
    </Suspense>
  );
}
