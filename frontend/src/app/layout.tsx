import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers, themeInitScript } from "@/components/providers";
import { brand } from "@/lib/brand";

const url = process.env.NEXT_PUBLIC_SITE_URL || `https://${brand.domain}`;

export const metadata: Metadata = {
  metadataBase: new URL(url),
  title: { default: `${brand.name} – ${brand.tagline_de}`, template: `%s · ${brand.name}` },
  description: "Finde heraus, wo deine Daten im Netz auffindbar sind, und lass sie Schritt für Schritt löschen. DSGVO-konform, auf Deutsch, EU-Hosting.",
  applicationName: brand.name,
  manifest: "/manifest.webmanifest",
  icons: { icon: [{ url: "/icons/icon.svg", type: "image/svg+xml" }, { url: "/icons/icon-192.png", sizes: "192x192" }], apple: "/icons/apple-touch-icon.png" },
  openGraph: { type: "website", locale: "de_DE", siteName: brand.name, images: [{ url: "/og.png", width: 1200, height: 630 }] },
  twitter: { card: "summary_large_image", images: ["/og.png"] },
  appleWebApp: { capable: true, title: brand.name, statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f7f9fc" }, { media: "(prefers-color-scheme: dark)", color: "#0b1120" }],
  width: "device-width", initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
