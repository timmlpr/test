"use client";
import { useState } from "react";
import { CheckCircle2, Clock, Trash2 } from "lucide-react";
import { Button } from "../ui/button";
import { Checkbox, Input, Select } from "../ui/input";
import { Alert } from "../ui/misc";
import { Badge } from "../ui/badge";
import { ErrorNotice } from "../notice";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

type Ident = { id: string; kind: string; value: string; verified: boolean };
const KINDS = ["name", "email", "phone", "city", "username", "domain"];

/** Add/verify own identifiers. Mandatory "these are my own data" checkbox (timestamped consent server-side). */
export function Identifiers({ onChange }: { onChange?: () => void }) {
  const { t } = useT();
  const list = useApi<Ident[]>("/profile/identifiers");
  const [kind, setKind] = useState("name");
  const [value, setValue] = useState("");
  const [own, setOwn] = useState(false);
  const [pending, setPending] = useState<Record<string, any>>({});
  const [codes, setCodes] = useState<Record<string, string>>({});
  const { run, busy, error } = useAction();
  const reload = async () => { await list.reload(); onChange?.(); };

  return (
    <div className="space-y-4">
      <form className="grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-[140px_1fr_auto]" onSubmit={(e) => { e.preventDefault(); run(async () => {
        const r = await api<any>("/profile/identifiers", { body: { kind, value, own_data: own } });
        if (r.pending_reason) setPending((p) => ({ ...p, [r.id]: r }));
        setValue(""); setOwn(false); await reload();
      }); }}>
        <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label={t("profile.kind")}>{KINDS.map((k) => <option key={k} value={k}>{t(`kind.${k}`)}</option>)}</Select>
        <Input value={value} onChange={(e) => setValue(e.target.value)} required placeholder={t(`kind.${kind}`)} aria-label={t("profile.value")} />
        <Button disabled={busy || !own}>{t("profile.add")}</Button>
        <div className="sm:col-span-3"><Checkbox checked={own} onChange={(e) => setOwn(e.target.checked)} label={<><strong>{t("onb.own")}</strong> <span className="text-muted-foreground">{t("onb.ownHint")}</span></>} /></div>
      </form>
      <ErrorNotice error={error} />
      <ul className="space-y-2">
        {(list.data ?? []).map((i) => (
          <li key={i.id} className="rounded-lg border bg-card p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="muted">{t(`kind.${i.kind}`)}</Badge>
              <span className="min-w-0 flex-1 truncate font-medium">{i.value}</span>
              {i.verified ? <Badge variant="ok"><CheckCircle2 className="h-3 w-3" />{t("profile.verified")}</Badge> : <Badge variant="warn"><Clock className="h-3 w-3" />{t("profile.pending")}</Badge>}
              <button className="rounded p-1.5 hover:bg-muted" aria-label={`${t("common.delete")}: ${i.value}`} onClick={() => run(async () => { await api(`/profile/identifiers/${i.id}`, { method: "DELETE" }); await reload(); })}>
                <Trash2 className="h-4 w-4" /></button>
            </div>
            {!i.verified && (
              <div className="mt-2 space-y-2 text-sm">
                {pending[i.id]?.pending_reason && <p className="text-muted-foreground">{t(`pending.${pending[i.id].pending_reason}`)}</p>}
                {pending[i.id]?.dns_txt && <code className="block break-all rounded bg-muted p-2">{pending[i.id].dns_txt}</code>}
                {pending[i.id]?.dev_hint && <Alert>{pending[i.id].dev_hint}</Alert>}
                {i.kind === "email" && <p className="text-muted-foreground">{t("pending.check_inbox")}</p>}
                {i.kind !== "email" && (
                  <div className="flex gap-2">
                    {i.kind === "phone" && <Input className="max-w-32" value={codes[i.id] ?? ""} onChange={(e) => setCodes({ ...codes, [i.id]: e.target.value })} placeholder={t("profile.code")} inputMode="numeric" aria-label={t("profile.code")} />}
                    <Button size="sm" variant="outline" onClick={() => run(async () => { await api(`/profile/identifiers/${i.id}/verify`, { body: { code: codes[i.id] } }); await reload(); })}>{t("profile.verify")}</Button>
                  </div>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
