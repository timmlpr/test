import type { Metadata } from "next";
import Link from "next/link";
import { posts } from "@/content/blog";

export const metadata: Metadata = { title: "Ratgeber", description: "Verständliche Tipps zu Datenschutz, Datenlecks, Lösch-Anfragen und Sicherheit." };

export default function Blog() {
  return (
    <div className="container max-w-3xl py-12">
      <h1 className="text-3xl font-bold">Ratgeber</h1>
      <p className="mt-2 text-muted-foreground">Kurz, sachlich, ohne Panik: So schützt du deine Daten.</p>
      <ul className="mt-8 space-y-4">
        {posts.map((p) => (
          <li key={p.slug} className="rounded-lg border bg-card p-5">
            <Link href={`/blog/${p.slug}`} className="text-lg font-semibold hover:text-primary">{p.title}</Link>
            <p className="mt-1 text-sm text-muted-foreground">{p.description}</p>
            <p className="mt-2 text-xs text-muted-foreground">{new Date(p.date).toLocaleDateString("de-DE")} · {p.minutes} Min. Lesezeit</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
