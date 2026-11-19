"use client";
// Learning widgets: flashcard review (SM-2), quiz, timed mock exam with grading.
import { Clock, RotateCcw, Trophy } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "./providers";
import { Badge, Button, Card, cn, Empty, Input, Progress, Spinner, Textarea } from "./ui";

interface CardT { id: number; module_id: number; front: string; back: string; source: { label?: string }; due: string; interval_days: number }

export function FlashcardReview({ moduleId }: { moduleId?: number }) {
  const [cards, setCards] = useState<CardT[] | null>(null);
  const [i, setI] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const shownAt = useRef(Date.now());

  const load = useCallback(() => {
    api.get<CardT[]>(`/learn/flashcards?due_only=true${moduleId ? `&module_id=${moduleId}` : ""}`).then((c) => {
      setCards(c);
      setI(0);
      setFlipped(false);
    });
  }, [moduleId]);
  useEffect(load, [load]);

  if (!cards) return <Spinner />;
  if (i >= cards.length)
    return (
      <Empty icon={<Trophy className="h-8 w-8 text-sicher" />} title={cards.length ? "Alle fälligen Karten erledigt!" : "Keine Karten fällig"}>
        <Button variant="outline" className="mt-2" onClick={load}><RotateCcw className="h-4 w-4" /> Neu laden</Button>
      </Empty>
    );
  const c = cards[i];
  const grade = async (g: number) => {
    await api.post(`/learn/flashcards/${c.id}/review`, { grade: g, seconds: (Date.now() - shownAt.current) / 1000 });
    setFlipped(false);
    setI(i + 1);
    shownAt.current = Date.now();
  };
  return (
    <div className="mx-auto max-w-2xl space-y-3">
      <div className="flex items-center gap-2 text-sm text-muted">
        <Progress value={i / cards.length} /> <span className="shrink-0">{i + 1}/{cards.length}</span>
      </div>
      <button
        onClick={() => setFlipped(!flipped)}
        className="flex min-h-64 w-full flex-col items-center justify-center rounded-2xl border border-border bg-surface p-6 text-center shadow-sm"
        aria-label={flipped ? "Antwort" : "Frage – tippen zum Umdrehen"}
      >
        <p className="mb-2 text-xs uppercase tracking-wide text-muted">{flipped ? "Antwort" : "Frage"}</p>
        <p className={cn("text-xl", flipped ? "font-normal" : "font-semibold")}>{flipped ? c.back : c.front}</p>
        {flipped && c.source?.label && <p className="mt-3 text-xs text-muted">Quelle: {c.source.label}</p>}
        {!flipped && <p className="mt-4 text-sm text-muted">Tippen zum Umdrehen</p>}
      </button>
      {flipped && (
        <div className="grid grid-cols-4 gap-2">
          <Button variant="danger" onClick={() => grade(1)}>Nochmal</Button>
          <Button variant="secondary" onClick={() => grade(3)}>Schwer</Button>
          <Button variant="secondary" onClick={() => grade(4)}>Gut</Button>
          <Button onClick={() => grade(5)}>Leicht</Button>
        </div>
      )}
    </div>
  );
}

interface QuizItem { type: "mc" | "cloze" | "open"; question: string; options?: string[]; answer?: number; answer_text?: string; solution?: string; points: number; source?: { label?: string } }

export function Quiz({ moduleId }: { moduleId: number }) {
  const [items, setItems] = useState<QuizItem[] | null>(null);
  const [answers, setAnswers] = useState<Record<number, string | number>>({});
  const [checked, setChecked] = useState(false);
  const start = useRef(Date.now());
  const load = useCallback(() => {
    setItems(null);
    setChecked(false);
    setAnswers({});
    start.current = Date.now();
    api.get<{ items: QuizItem[] }>(`/learn/quiz/${moduleId}`).then((r) => setItems(r.items));
  }, [moduleId]);
  useEffect(load, [load]);
  if (!items) return <Spinner />;
  if (!items.length) return <Empty title="Zu wenig Material für ein Quiz">Lade Folien hoch oder erstelle Karteikarten.</Empty>;
  const correct = items.filter((it, i) => (it.type === "mc" ? answers[i] === it.answer : String(answers[i] || "").trim().toLowerCase() === (it.answer_text || "").toLowerCase())).length;
  const check = async () => {
    setChecked(true);
    await api.post("/learn/quiz/result", { module_id: moduleId, correct, total: items.length, minutes: (Date.now() - start.current) / 60000 });
  };
  return (
    <div className="space-y-3">
      {items.map((it, i) => (
        <Card key={i}>
          <p className="mb-2 font-medium">{i + 1}. {it.question}</p>
          {it.type === "mc" ? (
            <div className="grid gap-2">
              {it.options!.map((o, j) => {
                const sel = answers[i] === j;
                const right = checked && j === it.answer;
                const wrong = checked && sel && j !== it.answer;
                return (
                  <button key={j} disabled={checked} onClick={() => setAnswers({ ...answers, [i]: j })}
                    className={cn("min-h-11 rounded-xl border px-3 py-2 text-left text-sm", sel ? "border-primary bg-primary/5" : "border-border", right && "border-sicher bg-sicher-bg", wrong && "border-unsicher bg-unsicher-bg")}>
                    {o}
                  </button>
                );
              })}
            </div>
          ) : (
            <Input disabled={checked} value={String(answers[i] || "")} onChange={(e) => setAnswers({ ...answers, [i]: e.target.value })} placeholder="Lücke ausfüllen" />
          )}
          {checked && it.type === "cloze" && <p className="mt-2 text-sm">Lösung: <b>{it.answer_text}</b></p>}
          {checked && it.source?.label && <p className="mt-1 text-xs text-muted">Quelle: {it.source.label}</p>}
        </Card>
      ))}
      <div className="flex items-center gap-3">
        {!checked ? <Button onClick={check}>Auswerten</Button> : <Badge className="px-3 py-1 text-base">{correct} / {items.length} richtig</Badge>}
        <Button variant="outline" onClick={load}><RotateCcw className="h-4 w-4" /> Neues Quiz</Button>
      </div>
    </div>
  );
}

interface Mock { id: number; title: string; minutes: number; items: QuizItem[]; started_at: string; submitted_at: string | null; score: number | null; grade: string | null; feedback: { points: number; max: number; feedback: string }[]; answers: Record<string, string | number> }

export function MockExam({ moduleId }: { moduleId: number }) {
  const { toast } = useApp();
  const [exam, setExam] = useState<Mock | null>(null);
  const [history, setHistory] = useState<Mock[]>([]);
  const [answers, setAnswers] = useState<Record<string, string | number>>({});
  const [left, setLeft] = useState(0);
  const [minutes, setMinutes] = useState(30);

  const loadHistory = useCallback(() => api.get<Mock[]>(`/learn/mock?module_id=${moduleId}`).then(setHistory), [moduleId]);
  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const submit = useCallback(async () => {
    if (!exam) return;
    const r = await api.post<Mock>(`/learn/mock/${exam.id}/submit`, { answers });
    setExam(r);
    loadHistory();
  }, [exam, answers, loadHistory]);

  useEffect(() => {
    if (!exam || exam.submitted_at) return;
    const end = new Date(exam.started_at + "Z").getTime() + exam.minutes * 60000;
    const t = setInterval(() => {
      const l = Math.max(0, Math.round((end - Date.now()) / 1000));
      setLeft(l);
      if (l === 0) {
        clearInterval(t);
        toast("Zeit abgelaufen – Klausur wird abgegeben.", "info");
        submit();
      }
    }, 1000);
    return () => clearInterval(t);
  }, [exam, submit, toast]);

  const start = async () => {
    try {
      setAnswers({});
      setExam(await api.post<Mock>("/learn/mock", { module_id: moduleId, minutes }));
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  if (!exam)
    return (
      <div className="space-y-4">
        <Card className="flex flex-wrap items-end gap-3">
          <div>
            <p className="mb-1 text-sm font-medium">Bearbeitungszeit (Minuten)</p>
            <Input type="number" min={5} max={180} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} className="w-28" />
          </div>
          <Button onClick={start}><Clock className="h-4 w-4" /> Probeklausur starten</Button>
        </Card>
        {history.length > 0 && (
          <Card>
            <p className="mb-2 font-semibold">Bisherige Versuche</p>
            <ul className="divide-y divide-border">
              {history.map((h) => (
                <li key={h.id} className="flex items-center justify-between py-2 text-sm">
                  <span>{h.title} · {new Date(h.started_at + "Z").toLocaleDateString("de-DE")}</span>
                  <span className="font-semibold">{h.grade ? `Note ${h.grade} (${h.score} %)` : "nicht abgegeben"}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    );

  const done = !!exam.submitted_at;
  return (
    <div className="space-y-3">
      <Card className="sticky top-2 z-10 flex items-center justify-between">
        <span className="font-semibold">{exam.title}</span>
        {done ? (
          <span className="text-lg font-bold">Note {exam.grade} · {exam.score} %</span>
        ) : (
          <span className={cn("tabular-nums text-lg font-bold", left < 120 && "text-unsicher")}>
            <Clock className="mr-1 inline h-4 w-4" />{Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}
          </span>
        )}
      </Card>
      {exam.items.map((it, i) => (
        <Card key={i}>
          <p className="mb-2 font-medium">{i + 1}. {it.question} <span className="text-sm text-muted">({it.points} P.)</span></p>
          {it.type === "mc" ? (
            <div className="grid gap-2">
              {it.options!.map((o, j) => (
                <button key={j} disabled={done} onClick={() => setAnswers({ ...answers, [i]: j })}
                  className={cn("min-h-11 rounded-xl border px-3 py-2 text-left text-sm", (done ? exam.answers[i] : answers[i]) === j ? "border-primary bg-primary/5" : "border-border")}>
                  {o}
                </button>
              ))}
            </div>
          ) : it.type === "open" ? (
            <Textarea disabled={done} value={String((done ? exam.answers[i] : answers[i]) || "")} onChange={(e) => setAnswers({ ...answers, [i]: e.target.value })} placeholder="Antwort im Gutachtenstil …" />
          ) : (
            <Input disabled={done} value={String((done ? exam.answers[i] : answers[i]) || "")} onChange={(e) => setAnswers({ ...answers, [i]: e.target.value })} />
          )}
          {done && exam.feedback[i] && (
            <p className={cn("mt-2 text-sm", exam.feedback[i].points >= exam.feedback[i].max ? "text-sicher" : "text-muted")}>
              {exam.feedback[i].points}/{exam.feedback[i].max} P. – {exam.feedback[i].feedback}
            </p>
          )}
        </Card>
      ))}
      {done ? <Button variant="outline" onClick={() => setExam(null)}>Zurück zur Übersicht</Button> : <Button size="lg" onClick={submit}>Abgeben</Button>}
    </div>
  );
}
