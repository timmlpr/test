import type { MetadataRoute } from "next";
import brand from "@/brand.json";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: brand.name,
    short_name: brand.short_name,
    description: brand.tagline,
    lang: "de",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    background_color: brand.colors.background,
    theme_color: brand.colors.background,
    categories: ["education", "productivity"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Live-Modus starten", url: "/live", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Eingang", url: "/inbox", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
    // Web Share Target (Android/desktop Chromium; iOS uses the Shortcut link from Einstellungen → Eingang)
    share_target: {
      action: "/api/inbox/share",
      method: "POST",
      enctype: "multipart/form-data",
      params: { title: "title", text: "text", url: "url", files: [{ name: "files", accept: ["application/pdf", "image/*", "audio/*", ".docx", ".pptx", ".txt"] }] },
    },
  } as MetadataRoute.Manifest;
}
