import type { MetadataRoute } from "next";
import { brand } from "@/lib/brand";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: brand.name, short_name: brand.name, description: brand.tagline_de, start_url: "/app", scope: "/", display: "standalone",
    background_color: "#f7f9fc", theme_color: "#2563eb", lang: "de", categories: ["security", "utilities"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [{ name: "Betrugs-Check", url: "/app/scam" }, { name: "Scan", url: "/app/scan" }],
  };
}
