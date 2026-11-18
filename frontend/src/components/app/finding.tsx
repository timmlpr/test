"use client";
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { Badge, RiskBadge } from "../ui/badge";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

export type Finding = {
  id: string; module: string; source: string; title: string; url: string | null; data_types: string[]; risk: string; details: any;
  found_at: string; occurred_at: string | null; status: string; tags: string[]; note: string | null; attributable: boolean; is_demo: boolean;
};

export const DT: Record<string, string> = {
  password: "Passwort", payment: "Bankdaten", id_document: "Ausweis", health: "Gesundheit", address: "Adresse", phone: "Telefon",
  birthdate: "Geburtsdatum", location: "Standort", ip: "IP-Adresse", name: "Name", email: "E-Mail", username: "Benutzername",
  security_qa: "Sicherheitsfragen", gender: "Geschlecht", web: "Webseite", employers: "Arbeitgeber", job_titles: "Berufsbezeichnung",
};

export function FindingRow({ f, actions }: { f: Finding; actions?: React.ReactNode }) {
  const { t } = useT();
  return (
    <li id={f.id} className="rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-start gap-2">
        <RiskBadge risk={f.risk} label={t(`risk.${f.risk}`)} />
        {!f.attributable && <Badge variant="muted">{t("common.notAttributable")}</Badge>}
        {f.is_demo && <Badge variant="warn">{t("common.demo")}</Badge>}
        {f.status === "done" && <Badge variant="ok">{t("common.done")}</Badge>}
        <span className="ml-auto text-xs text-muted-foreground">{f.source} · {fmtDate(f.found_at)}</span>
      </div>
      <p className="mt-2 font-medium">{f.title}</p>
      {f.details?.snippet && <p className="mt-1 text-sm text-muted-foreground">{f.details.snippet}</p>}
      <div className="mt-2 flex flex-wrap gap-1">{f.data_types.map((d) => <Badge key={d} variant="outline">{DT[d] ?? d}</Badge>)}</div>
      {f.url && <a href={f.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 break-all text-sm text-primary underline">{f.url}<ExternalLink className="h-3 w-3" /></a>}
      {actions && <div className="mt-3 flex flex-wrap gap-2">{actions}</div>}
    </li>
  );
}

export function RequestLink({ f }: { f: Finding }) {
  const { t } = useT();
  return <Link href={`/app/requests/new?finding=${f.id}`} className="text-sm font-medium text-primary underline">{t("results.request")}</Link>;
}
