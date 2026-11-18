"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

export default function Abuse() {
  const { t } = useT();
  const [msg, setMsg] = useState("");
  const [contact, setContact] = useState("");
  const [done, setDone] = useState(false);
  const { run, busy, error } = useAction();
  return (
    <div className="container max-w-xl py-12">
      <h1 className="text-3xl font-bold">{t("abuse.title")}</h1>
      <p className="mt-2 text-muted-foreground">{t("abuse.explain")}</p>
      {done ? <Alert kind="ok" className="mt-6">Danke. Wir prüfen deine Meldung und melden uns, falls du Kontaktdaten angegeben hast.</Alert> : (
        <form className="mt-6 space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/abuse", { body: { message: msg, contact: contact || null } }); setDone(true); }); }}>
          <Field label="Was ist passiert?" htmlFor="a-msg"><Textarea id="a-msg" required minLength={10} value={msg} onChange={(e) => setMsg(e.target.value)} /></Field>
          <Field label="Kontakt für Rückfragen (optional)" htmlFor="a-c"><Input id="a-c" value={contact} onChange={(e) => setContact(e.target.value)} /></Field>
          <ErrorNotice error={error} />
          <Button type="submit" disabled={busy}>Meldung senden</Button>
        </form>
      )}
    </div>
  );
}
