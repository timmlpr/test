"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, Send, Volume2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, Dialog } from "@/components/ui/misc";
import { Badge } from "@/components/ui/badge";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

type Msg = { role: "user" | "bot"; text: string; citations?: any[]; action?: { href: string; label: string }; refused?: boolean; mode?: string };

export default function Assistant() {
  const { t } = useT();
  const status = useApi<any>("/assistant/status");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [listening, setListening] = useState(false);
  const [askMic, setAskMic] = useState(false);
  const [voice, setVoice] = useState(false);
  const rec = useRef<any>(null);
  const end = useRef<HTMLDivElement>(null);
  const { run, busy, error } = useAction();
  const speechOk = typeof window !== "undefined" && ("webkitSpeechRecognition" in window || "SpeechRecognition" in window);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const send = (text: string, fromVoice = false) => run(async () => {
    if (!text.trim()) return;
    setMsgs((m) => [...m, { role: "user", text }]);
    setInput("");
    const r = await api<any>("/assistant/chat", { body: { message: text, voice: fromVoice } });
    setMsgs((m) => [...m, { role: "bot", text: r.text, citations: r.citations, action: r.action, refused: r.refused, mode: r.mode }]);
    if (fromVoice || voice) speak(r.text);
  });
  const speak = (text: string) => { if (!("speechSynthesis" in window)) return; const u = new SpeechSynthesisUtterance(text); u.lang = "de-DE"; speechSynthesis.cancel(); speechSynthesis.speak(u); };

  /** Microphone only after explicit consent. Audio is processed by the browser's speech service; Fadeprint stores no audio. */
  const startMic = async () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return;
    await api("/profile/consent", { body: { kind: "mic", granted: true } });
    const r = new SR(); r.lang = "de-DE"; r.interimResults = false; r.maxAlternatives = 1;
    r.onresult = (e: any) => { const txt = e.results[0][0].transcript; setInput(txt); send(txt, true); };
    r.onend = () => setListening(false);
    rec.current = r; r.start(); setListening(true);
  };
  return (
    <div className="flex h-[calc(100vh-10rem)] flex-col lg:h-[calc(100vh-7rem)]">
      <PageHeader title={t("ai.title")} explain={t("ai.explain")} premium next={!msgs.length ? { label: t("ai.suggest1"), onClick: () => send(t("ai.suggest1")) } : undefined} />
      {status.data && (status.data.available ? <Alert className="mb-3">{t("ai.notice")}</Alert> : <p className="mb-3 text-xs text-muted-foreground">{t("ai.classic")}</p>)}
      <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border bg-card p-4" aria-live="polite">
        {!msgs.length && <div className="flex flex-wrap gap-2">{["ai.suggest1", "ai.suggest2", "ai.suggest3"].map((k) => <Button key={k} variant="outline" size="sm" onClick={() => send(t(k))}>{t(k)}</Button>)}</div>}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-primary-foreground" : "max-w-[90%] rounded-lg bg-muted px-3 py-2"}>
            <p className="whitespace-pre-wrap text-sm">{m.text}</p>
            {m.refused && <Badge variant="warn" className="mt-1">Nur eigene Daten</Badge>}
            {!!m.citations?.length && <ul className="mt-2 space-y-0.5 text-xs">{m.citations.map((c) => <li key={c.id}>Quelle: <Link className="underline" href={`/app/results#${c.id}`}>{c.title}</Link></li>)}</ul>}
            {m.action && <Link href={m.action.href} className="mt-2 inline-block text-sm font-medium text-primary underline">{m.action.label} →</Link>}
            {m.role === "bot" && <button className="ml-2 align-middle text-muted-foreground" onClick={() => speak(m.text)} aria-label={t("ai.speak")}><Volume2 className="inline h-4 w-4" /></button>}
          </div>
        ))}
        <div ref={end} />
      </div>
      <ErrorNotice error={error} />
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("ai.placeholder")} aria-label={t("ai.placeholder")} />
        {speechOk && <Button type="button" variant="outline" size="icon" aria-label={t("ai.mic")} onClick={() => (listening ? rec.current?.stop() : setAskMic(true))}>
          {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}</Button>}
        <Button type="button" variant={voice ? "default" : "outline"} size="icon" aria-pressed={voice} aria-label={t("ai.speak")} onClick={() => setVoice(!voice)}><Volume2 className="h-4 w-4" /></Button>
        <Button disabled={busy} aria-label={t("ai.send")}><Send className="h-4 w-4" /></Button>
      </form>
      <p className="mt-1 text-xs text-muted-foreground">Der Assistent führt keine Aktionen selbst aus. Er verlinkt nur – Löschen, Senden und Bezahlen bestätigst du immer selbst.</p>
      <Dialog open={askMic} onClose={() => setAskMic(false)} title={t("ai.mic")}>
        <p className="mb-4 text-sm">{t("ai.micConsent")}</p>
        <div className="flex gap-2"><Button onClick={() => { setAskMic(false); startMic(); }}>{t("common.yes")}</Button><Button variant="outline" onClick={() => setAskMic(false)}>{t("common.no")}</Button></div>
      </Dialog>
    </div>
  );
}
