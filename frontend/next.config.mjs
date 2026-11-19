/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
// Default: never framed. The private Hugging Face demo build sets FRAME_ANCESTORS so the Space page may embed it.
const frameAncestors = process.env.FRAME_ANCESTORS || "'none'";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  ...(process.env.FRAME_ANCESTORS ? [] : [{ key: "X-Frame-Options", value: "DENY" }]),
  { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=(self), payment=(self)" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'" + (process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""),
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      "font-src 'self'",
      "connect-src 'self'",
      `frame-ancestors ${frameAncestors}`,
      "form-action 'self' https://checkout.stripe.com https://accounts.google.com https://appleid.apple.com",
      "base-uri 'self'",
      "worker-src 'self'",
    ].join("; "),
  },
];

export default {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache" }, { key: "Service-Worker-Allowed", value: "/" }] },
    ];
  },
};
