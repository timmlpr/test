"use client";
import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Alert, Progress } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

/** Strength estimate (local): length, character classes, common patterns. */
function strength(pw: string): number {
  if (!pw) return 0;
  let bits = 0;
  const pool = (/[a-z]/.test(pw) ? 26 : 0) + (/[A-Z]/.test(pw) ? 26 : 0) + (/\d/.test(pw) ? 10 : 0) + (/[^A-Za-z0-9]/.test(pw) ? 33 : 0);
  bits = pw.length * Math.log2(Math.max(pool, 1));
  if (/^(.)\1+$/.test(pw) || /(1234|abcd|qwert|passw|hallo|letmein|asdf)/i.test(pw)) bits *= 0.4;
  return bits < 28 ? 0 : bits < 40 ? 1 : bits < 60 ? 2 : bits < 80 ? 3 : 4;
}

async function sha1(s: string) {
  const h = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("").toUpperCase();
}

export default function Passwords() {
  const { t } = useT();
  const [pw, setPw] = useState("");
  const [show, setShow] = useState(false);
  const [count, setCount] = useState<number | null>(null);
  const [err, setErr] = useState(false);
  const [many, setMany] = useState("");
  const [reuse, setReuse] = useState<number | null>(null);
  const s = strength(pw);

  const check = async () => {
    setErr(false); setCount(null);
    const h = await sha1(pw);
    try {
      const body = await api<string>(`/password/range/${h.slice(0, 5)}`);
      const line = body.split("\n").find((l) => l.startsWith(h.slice(5)));
      setCount(line ? parseInt(line.split(":")[1], 10) : 0);
    } catch { setErr(true); }
  };
  const checkReuse = () => {
    const list = many.split("\n").map((l) => l.trim()).filter(Boolean);
    const norm = list.map((p) => p.toLowerCase().replace(/[\d!?.]+$/, ""));
    setReuse(norm.length - new Set(norm).size);
  };
  return (
    <div className="space-y-6">
      <PageHeader title={t("pw.title")} explain={t("pw.explain")} next={{ label: t("nav.checklist"), href: "/app/checklist" }} />
      <Card>
        <CardContent className="space-y-4 pt-5">
          <div className="flex gap-2">
            <Input type={show ? "text" : "password"} value={pw} onChange={(e) => { setPw(e.target.value); setCount(null); }} placeholder={t("pw.input")} aria-label={t("pw.input")} autoComplete="off" />
            <Button variant="outline" size="icon" onClick={() => setShow(!show)} aria-label={show ? "Verbergen" : "Anzeigen"}>{show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</Button>
            <Button onClick={check} disabled={!pw}>{t("pw.check")}</Button>
          </div>
          <div><p className="mb-1 text-sm">{t("pw.strength")}: <strong>{t(`pw.s${s}`)}</strong></p><Progress value={(s + 1) * 20} label={t("pw.strength")} /></div>
          {count !== null && (count > 0 ? <Alert kind="bad">{t("pw.pwned", { n: count.toLocaleString("de-DE") })}</Alert> : <Alert kind="ok">{t("pw.safe")}</Alert>)}
          {err && <Alert kind="warn">{t("err.source_unavailable")}</Alert>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">{t("pw.reuse")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("pw.reuseHint")}</p>
          <Textarea value={many} onChange={(e) => { setMany(e.target.value); setReuse(null); }} className="font-mono" aria-label={t("pw.reuse")} autoComplete="off" spellCheck={false} />
          <Button variant="outline" onClick={checkReuse} disabled={!many}>{t("pw.check")}</Button>
          {reuse !== null && <Alert kind={reuse ? "warn" : "ok"}>{reuse ? t("pw.reuseFound", { n: reuse }) : t("pw.reuseNone")}</Alert>}
        </CardContent>
      </Card>
    </div>
  );
}
