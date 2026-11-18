import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { postBySlug, posts } from "@/content/blog";
import { markdown } from "@/lib/markdown";
import { brand } from "@/lib/brand";

export const dynamicParams = false;
export function generateStaticParams() { return posts.map((p) => ({ slug: p.slug })); }

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const p = postBySlug((await params).slug);
  return p ? { title: p.title, description: p.description, openGraph: { type: "article", title: p.title, description: p.description } } : {};
}

export default async function Post({ params }: { params: Promise<{ slug: string }> }) {
  const p = postBySlug((await params).slug);
  if (!p) notFound();
  const ld = { "@context": "https://schema.org", "@type": "Article", headline: p.title, description: p.description, datePublished: p.date, inLanguage: "de",
    publisher: { "@type": "Organization", name: brand.name } };
  return (
    <article className="container max-w-3xl py-12">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ld) }} />
      <Link href="/blog" className="text-sm text-primary">← Alle Artikel</Link>
      <h1 className="mt-4 text-3xl font-bold">{p.title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{new Date(p.date).toLocaleDateString("de-DE")} · {p.minutes} Min. Lesezeit</p>
      <div className="prose-fp mt-8" dangerouslySetInnerHTML={{ __html: markdown(p.body) }} />
      <aside className="mt-10 rounded-lg border bg-card p-4 text-sm">
        <p className="font-semibold">Quellen</p>
        <ul className="mt-2 list-disc pl-5">{p.sources.map((s) => <li key={s}><a href={s} className="break-all text-primary underline" rel="noopener noreferrer" target="_blank">{s}</a></li>)}</ul>
      </aside>
      <div className="mt-8 rounded-lg border border-primary/20 bg-primary/5 p-5">
        <p className="font-semibold">Nächster Schritt</p>
        <p className="mt-1 text-sm text-muted-foreground">Prüfe kostenlos, wo deine eigenen Daten auftauchen.</p>
        <Link href="/register" className="mt-3 inline-block font-medium text-primary underline">Kostenlos starten</Link>
      </div>
    </article>
  );
}
