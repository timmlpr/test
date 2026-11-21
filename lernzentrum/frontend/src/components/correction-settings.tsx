"use client";
// Settings for the Kontext-Korrektur: on/off, aggressiveness, thresholds, AI layer, own vocabulary, learned rules,
// export/import.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Module } from "@/lib/types";
import { useApp } from "./providers";
import { Button, Card, CardTitle, Input, Label, Select, Toggle } from "./ui";

interface CS { enabled: boolean; mode: string; auto: number; mark: number; llm: boolean; max_edit_ratio: number }

export function CorrectionSettings() {
  const { toast } = useApp();
  const [s, setS] = useState<CS | null>(null);
  const [vocab, setVocab] = useState<{ term: string; module_id: number | null }[]>([]);
  const [rules, setRules] = useState<{ from: string; to: string; module_id: number | null }[]>([]);
  const [mods, setMods] = useState<Module[]>([]);
  const [term, setTerm] = useState("");
  const [mid, setMid] = useState("");
  const file = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api.get<CS>("/correction/settings").then(setS);
    api.get<typeof vocab>("/correction/vocabulary").then(setVocab);
    api.get<typeof rules>("/correction/rules").then(setRules);
  }, []);
  useEffect(() => {
    load();
    api.get<Module[]>("/modules").then(setMods);
  }, [load]);
  if (!s) return null;
  const save = async (patch: Partial<CS>) => {
    try {
      setS(await api.put<CS>("/correction/settings", patch));
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };
  const modName = (id: number | null) => (id ? mods.find((m) => m.id === id)?.short || "?" : "alle Module");

  return (
    <Card className="space-y-3 lg:col-span-2">
      <CardTitle>Kontext-Korrektur (Transkript)</CardTitle>
      <p className="text-sm text-muted">Korrigiert falsch erkannte Gesetzeszitate und Fachbegriffe, z. B. „§433 WWW“ → „§ 433 BGB“. Das Original bleibt immer erhalten.</p>
      <Toggle checked={s.enabled} onChange={(v) => save({ enabled: v })} label="Korrektur aktiv" />
      <div className="grid gap-3 sm:grid-cols-4">
        <div>
          <Label>Stil</Label>
          <Select value={s.mode} onChange={(e) => save({ mode: e.target.value })}>
            <option value="conservative">Vorsichtig</option><option value="balanced">Ausgewogen</option><option value="aggressive">Mutig</option>
          </Select>
        </div>
        <div><Label hint="%">Automatisch ab</Label><Input type="number" value={s.auto} onChange={(e) => setS({ ...s, auto: Number(e.target.value) })} onBlur={() => save({ auto: s.auto, mark: s.mark })} /></div>
        <div><Label hint="%">Markiert ab</Label><Input type="number" value={s.mark} onChange={(e) => setS({ ...s, mark: Number(e.target.value) })} onBlur={() => save({ auto: s.auto, mark: s.mark })} /></div>
        <div><Label hint="0–1">Max. KI-Änderung</Label><Input type="number" step="0.05" value={s.max_edit_ratio} onChange={(e) => setS({ ...s, max_edit_ratio: Number(e.target.value) })} onBlur={() => save({ max_edit_ratio: s.max_edit_ratio })} /></div>
      </div>
      <Toggle checked={s.llm} onChange={(v) => save({ llm: v })} label="KI-Prüfung unklarer Stellen (Gemini)" description="Nur bei unsicheren Stellen, gecacht; verbraucht Gemini-Kontingent." />
      <div>
        <p className="mb-1 font-medium">Eigenes Vokabular</p>
        <form className="flex flex-wrap gap-2" onSubmit={async (e) => { e.preventDefault(); setVocab(await api.post("/correction/vocabulary", { term, module_id: mid ? Number(mid) : null })); setTerm(""); }}>
          <Input className="min-w-[200px] flex-1" placeholder="z. B. Kaufpreisanspruch, Prof. Weber" value={term} onChange={(e) => setTerm(e.target.value)} />
          <Select className="w-44" value={mid} onChange={(e) => setMid(e.target.value)}>
            <option value="">alle Module</option>{mods.map((m) => <option key={m.id} value={m.id}>{m.short}</option>)}
          </Select>
          <Button type="submit" variant="outline" disabled={!term.trim()}>Hinzufügen</Button>
        </form>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {vocab.map((v) => (
            <button key={`${v.term}-${v.module_id}`} className="rounded-full border border-border px-2.5 py-1 text-sm" title="Entfernen"
              onClick={async () => setVocab(await api.del(`/correction/vocabulary?term=${encodeURIComponent(v.term)}${v.module_id ? `&module_id=${v.module_id}` : ""}`))}>
              {v.term} <span className="text-muted">· {modName(v.module_id)} ✕</span>
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="mb-1 font-medium">Gelernte Regeln („immer so korrigieren“)</p>
        {rules.length === 0 ? <p className="text-sm text-muted">Noch keine.</p> : (
          <ul className="space-y-1 text-sm">
            {rules.map((r) => (
              <li key={r.from} className="flex items-center gap-2">
                <span className="flex-1">{r.from} → <b>{r.to}</b> <span className="text-muted">· {modName(r.module_id)}</span></span>
                <Button size="sm" variant="ghost" onClick={async () => setRules(await api.del(`/correction/rules/${encodeURIComponent(r.from)}`))}>Löschen</Button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <a href="/api/correction/export" download="lernzentrum-vokabular.json"><Button variant="outline">Vokabular exportieren</Button></a>
        <Button variant="outline" onClick={() => file.current?.click()}>Importieren</Button>
        <input ref={file} type="file" accept="application/json" className="hidden" onChange={async (e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          try {
            const r = await api.post<{ vocabulary: number; rules: number }>("/correction/import", JSON.parse(await f.text()));
            toast(`${r.vocabulary} Begriffe, ${r.rules} Regeln importiert`, "ok");
            load();
          } catch (err) {
            toast((err as Error).message, "error");
          }
        }} />
      </div>
    </Card>
  );
}
