import type { MetadataRoute } from "next";
import { brand } from "@/lib/brand";
import { posts } from "@/content/blog";

export default function sitemap(): MetadataRoute.Sitemap {
  const url = process.env.NEXT_PUBLIC_SITE_URL || `https://${brand.domain}`;
  const pages = ["", "/preise", "/blog", "/kuendigen", "/missbrauch-melden", "/rechtliches/impressum", "/rechtliches/datenschutz", "/rechtliches/agb",
    "/rechtliches/widerruf", "/rechtliches/nutzungsbedingungen", "/rechtliches/keine-rechtsberatung"];
  return [
    ...pages.map((p) => ({ url: `${url}${p}`, changeFrequency: "monthly" as const, priority: p === "" ? 1 : 0.6 })),
    ...posts.map((p) => ({ url: `${url}/blog/${p.slug}`, lastModified: p.date, changeFrequency: "yearly" as const, priority: 0.5 })),
  ];
}
