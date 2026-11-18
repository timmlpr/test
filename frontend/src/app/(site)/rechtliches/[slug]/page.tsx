import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { markdown } from "@/lib/markdown";
import { brand } from "@/lib/brand";

const PAGES: Record<string, { file: string; title: string }> = {
  impressum: { file: "impressum.md", title: "Impressum" },
  datenschutz: { file: "datenschutz.md", title: "Datenschutzerklärung" },
  agb: { file: "agb.md", title: "Allgemeine Geschäftsbedingungen" },
  widerruf: { file: "widerruf.md", title: "Widerrufsbelehrung" },
  nutzungsbedingungen: { file: "nutzungsbedingungen.md", title: "Nutzungsbedingungen" },
  "keine-rechtsberatung": { file: "keine-rechtsberatung.md", title: "Hinweis: Keine Rechtsberatung" },
};

export const dynamicParams = false;
export function generateStaticParams() { return Object.keys(PAGES).map((slug) => ({ slug })); }
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const p = PAGES[(await params).slug];
  return p ? { title: p.title, robots: { index: false } } : {};
}

/** Fill operator placeholders from config/brand.json so legal texts never hard-code company data. */
function fill(md: string) {
  const o = brand.operator as Record<string, string | boolean>;
  return md.replace(/\{\{(\w+)\}\}/g, (_m, k) => (k === "brand" ? brand.name : k === "domain" ? brand.domain : k === "support_email" ? brand.support_email : String(o[k] ?? `[${k}]`)));
}

export default async function Legal({ params }: { params: Promise<{ slug: string }> }) {
  const p = PAGES[(await params).slug];
  if (!p) notFound();
  let md = "";
  try { md = readFileSync(join(process.cwd(), "src", "content", "legal", p.file), "utf8"); } catch { notFound(); }
  return (
    <div className="container max-w-3xl py-12">
      <div className="prose-fp" dangerouslySetInnerHTML={{ __html: markdown(fill(md)) }} />
    </div>
  );
}
