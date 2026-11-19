import type { Metadata, Viewport } from "next";
import brand from "@/brand.json";
import { Providers } from "@/components/providers";
import "./globals.css";

// iPad + iPhone launch images (portrait + landscape) for the "Add to Home Screen" app.
const SPLASH: [number, number, number, number][] = [
  [1024, 1366, 2048, 2732], [834, 1194, 1668, 2388], [820, 1180, 1640, 2360], [810, 1080, 1620, 2160],
  [744, 1133, 1488, 2266], [768, 1024, 1536, 2048], [393, 852, 1179, 2556], [430, 932, 1290, 2796], [390, 844, 1170, 2532],
];

export const metadata: Metadata = {
  title: { default: brand.name, template: `%s · ${brand.name}` },
  description: brand.tagline,
  applicationName: brand.name,
  manifest: "/manifest.webmanifest",
  icons: { icon: [{ url: "/favicon.png" }, { url: "/logo.svg", type: "image/svg+xml" }], apple: "/icons/apple-touch-icon.png" },
  appleWebApp: {
    capable: true,
    title: brand.short_name,
    statusBarStyle: "default",
    startupImage: SPLASH.flatMap(([w, h, pw, ph]) => [
      { url: `/splash/splash-${pw}x${ph}.png`, media: `(device-width: ${w}px) and (device-height: ${h}px) and (orientation: portrait)` },
      { url: `/splash/splash-${ph}x${pw}.png`, media: `(device-width: ${w}px) and (device-height: ${h}px) and (orientation: landscape)` },
    ]),
  },
  formatDetection: { telephone: false },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#f7f6f2",
};

// Applies theme/large type before first paint (no flash).
const boot = `try{var t=localStorage.getItem('lz-theme')||'system';var d=t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);if(d)document.documentElement.classList.add('dark');if(localStorage.getItem('lz-large')==='1')document.documentElement.classList.add('large-type')}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: boot }} />
        <meta name="mobile-web-app-capable" content="yes" />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
