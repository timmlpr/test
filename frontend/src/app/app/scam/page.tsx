"use client";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox, Field, Input, Switch, Textarea } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { TrafficLight } from "@/components/risk-gauge";
import { ErrorNotice } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

export default function Scam() {
  const { t } = useT();
  const { user } = useAuth();
  const cfg = useApi<any>("/config/public");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [useAi, setUseAi] = useState(false);
  const [family, setFamily] = useState(false);
  const [r, setR] = useState<any>(null);
  const { run, busy, error } = useAction();
  const aiOn = cfg.data?.ai?.available && user?.tier === "premium";
  return (
    <div className="space-y-6">
      <PageHeader title={t("scam.title")} explain={t("scam.explain")} next={r?.light === "red" ? { label: "Phishing melden (Verbraucherzentrale)", href: "https://www.verbraucherzentrale.de/phishing-radar" } : undefined} />
      <Card><CardContent className="space-y-4 pt-5">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => setR(await api("/scam/check", { body: { url: url || null, text: text || null, use_ai: useAi } }))); }}>
          <Field label={t("scam.url")} htmlFor="s-url"><Input id="s-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" inputMode="url" /></Field>
          <Field label={t("scam.text")} htmlFor="s-text"><Textarea id="s-text" value={text} onChange={(e) => setText(e.target.value)} /></Field>
          {aiOn && <Checkbox checked={useAi} onChange={(e) => setUseAi(e.target.checked)} label={<>{t("scam.ai")} <span className="block text-xs text-muted-foreground">{t("ai.notice")}</span></>} />}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button disabled={busy || (!url && !text)}>{t("scam.check")}</Button>
            <div className="w-56"><Switch checked={family} onChange={setFamily} label={t("scam.family")} /></div>
          </div>
        </form>
        <ErrorNotice error={error} />
      </CardContent></Card>
      {r && (family ? (
        <Card className="flex flex-col items-center gap-4 p-8 text-center"><TrafficLight light={r.light} big /><p className="text-xl font-semibold">{r.summary}</p></Card>
      ) : (
        <Card><CardContent className="space-y-4 pt-5">
          <div className="flex items-center gap-6"><TrafficLight light={r.light} /><p className="text-lg font-semibold">{r.summary}</p></div>
          {r.reasons.length > 0 && <ul className="list-disc space-y-1 pl-5 text-sm">{r.reasons.map((x: any) => <li key={x.key}>{x.text}</li>)}</ul>}
          {r.checks.map((c: any) => <p key={c.url} className="text-sm text-muted-foreground">{c.domain}: {c.age_days != null ? `${c.age_days} Tage alt` : "Alter unbekannt"}{c.registrar ? ` · ${c.registrar}` : ""}</p>)}
          {r.ai && <Alert><strong>KI-Einschätzung:</strong> {r.ai}</Alert>}
          <p className="text-xs text-muted-foreground">Quellen: {r.sources.join(", ")}</p>
          {r.missing_sources.length > 0 && <p className="text-xs text-muted-foreground">{t("scam.missing", { list: r.missing_sources.join(", ") })}</p>}
        </CardContent></Card>
      ))}
    </div>
  );
}
