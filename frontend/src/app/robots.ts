import type { MetadataRoute } from "next";
import { brand } from "@/lib/brand";

export default function robots(): MetadataRoute.Robots {
  const url = process.env.NEXT_PUBLIC_SITE_URL || `https://${brand.domain}`;
  return { rules: [{ userAgent: "*", allow: "/", disallow: ["/app", "/admin", "/api"] }], sitemap: `${url}/sitemap.xml` };
}
