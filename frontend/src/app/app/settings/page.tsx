"use client";
import { useState } from "react";
import { KeyRound, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/input";
import { Alert, Dialog } from "@/components/ui/misc";
import { Badge } from "@/components/ui/badge";
import { ErrorNotice } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { api, download } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { createPasskey, passkeysSupported } from "@/lib/webauthn";
import { fmtDate } from "@/lib/utils";

export default function Settings() {
  const { t, setForm, setLocale, locale } = useT();
  const { user, refresh, logout } = useAuth();
  const pks = useApi<any[]>("/auth/passkeys");
  const [totp, setTotp] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [pw, setPw] = useState({ current: "", new: "" });
  const [del, setDel] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const { run, busy, error } = useAction();
  if (!user) return null;
  const setAddress = (f: "du" | "sie") => run(async () => { await api("/profile/settings", { method: "PATCH", body: { address_form: f } }); setForm(f); refresh(); });
  return (
    <div className="space-y-6">
      <PageHeader title={t("set.title")} explain={t("set.explain")} next={!user.totp_enabled ? { label: `${t("set.2fa")}: ${t("set.2faSetup")}`, href: "#twofa" } : undefined} />
      {msg && <Alert kind="ok">{msg}</Alert>}
      <ErrorNotice error={error} />
      <Card><CardHeader><CardTitle className="text-base">{t("set.address")} & {t("set.language")}</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap gap-4">
          <Select value={user.address_form} onChange={(e) => setAddress(e.target.value as "du" | "sie")} className="w-40" aria-label={t("set.address")}><option value="du">{t("set.du")}</option><option value="sie">{t("set.sie")}</option></Select>
          <Select value={locale} onChange={(e) => { setLocale(e.target.value as "de" | "en"); api("/profile/settings", { method: "PATCH", body: { locale: e.target.value } }); }} className="w-40" aria-label={t("set.language")}>
            <option value="de">Deutsch</option><option value="en">English (Beta)</option></Select>
        </CardContent></Card>

      <Card id="twofa"><CardHeader><CardTitle className="text-base">{t("set.2fa")} {user.totp_enabled && <Badge variant="ok">{t("set.2faOn")}</Badge>}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {!user.totp_enabled && !totp && <Button onClick={() => run(async () => setTotp(await api("/auth/totp/setup", { method: "POST" })))}>{t("set.2faSetup")}</Button>}
          {totp && !codes && (
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run(async () => { const r = await api<any>("/auth/totp/enable", { body: { code } }); setCodes(r.recovery_codes); refresh(); }); }}>
              <p className="text-sm">{t("set.2faScan")}</p>
              <code className="block break-all rounded bg-muted p-2 text-sm">{totp.secret}</code>
              <a href={totp.otpauth_uri} className="text-sm text-primary underline">In Authenticator-App öffnen</a>
              <div className="flex gap-2"><Input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" className="max-w-40" aria-label="Code" /><Button>{t("common.save")}</Button></div>
            </form>
          )}
          {codes && <Alert kind="warn"><p className="font-medium">{t("set.recovery")}</p><pre className="mt-2 grid grid-cols-2 gap-1 font-mono text-sm">{codes.join("\n")}</pre></Alert>}
          {user.totp_enabled && !codes && (
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/auth/totp/disable", { body: { code } }); setCode(""); refresh(); }); }}>
              <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Code" className="max-w-40" aria-label="Code" /><Button variant="outline">Deaktivieren</Button>
            </form>
          )}
        </CardContent></Card>

      <Card><CardHeader><CardTitle className="text-base">{t("set.passkeys")}</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <ul className="space-y-1 text-sm">{(pks.data ?? []).map((p) => (
            <li key={p.id} className="flex items-center gap-2"><KeyRound className="h-4 w-4" />{p.name}<span className="text-muted-foreground">{fmtDate(p.created_at)}</span>
              <button className="ml-auto rounded p-1 hover:bg-muted" aria-label={`${t("common.delete")}: ${p.name}`} onClick={() => run(async () => { await api(`/auth/passkeys/${p.id}`, { method: "DELETE" }); pks.reload(); })}><Trash2 className="h-4 w-4" /></button></li>))}
          </ul>
          {passkeysSupported() && <Button variant="outline" onClick={() => run(async () => {
            const opts = await api("/auth/passkey/register/begin", { method: "POST" });
            const credential = await createPasskey(opts);
            await api("/auth/passkey/register/finish", { body: { credential, name: navigator.platform || "Passkey" } });
            pks.reload(); setMsg("Passkey gespeichert.");
          })}>{t("set.passkeyAdd")}</Button>}
        </CardContent></Card>

      <Card><CardHeader><CardTitle className="text-base">{t("set.password")}</CardTitle></CardHeader>
        <CardContent><form className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/auth/password", { body: pw }); setPw({ current: "", new: "" }); setMsg("Passwort geändert."); }); }}>
          <Input type="password" placeholder="Aktuelles Passwort" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} autoComplete="current-password" aria-label="Aktuelles Passwort" />
          <Input type="password" placeholder="Neues Passwort" minLength={10} value={pw.new} onChange={(e) => setPw({ ...pw, new: e.target.value })} autoComplete="new-password" aria-label="Neues Passwort" />
          <Button disabled={busy}>{t("common.save")}</Button></form></CardContent></Card>

      <Card><CardHeader><CardTitle className="text-base">Deine Daten</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => download("/profile/export", "tracelow-export.json")}>{t("set.export")}</Button>
          <Button variant="outline" onClick={() => run(async () => { await api("/auth/logout-all", { method: "POST" }); location.href = "/login"; })}>{t("set.logoutAll")}</Button>
          <Button variant="destructive" onClick={() => setDel(true)}>{t("set.delete")}</Button>
        </CardContent></Card>
      <Dialog open={del} onClose={() => setDel(false)} title={t("set.delete")}>
        <p className="mb-4 text-sm">{t("set.deleteConfirm")}</p>
        <div className="flex gap-2"><Button variant="destructive" onClick={() => run(async () => { await api("/profile", { method: "DELETE", body: { confirm: true } }); await logout(); })}>{t("common.delete")}</Button>
          <Button variant="outline" onClick={() => setDel(false)}>{t("common.cancel")}</Button></div>
      </Dialog>
    </div>
  );
}
