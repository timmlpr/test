import type { Config } from "tailwindcss";

const c = (v: string) => `hsl(var(--${v}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1rem", screens: { "2xl": "1200px" } },
    extend: {
      colors: {
        border: c("border"), input: c("input"), ring: c("ring"), background: c("background"), foreground: c("foreground"),
        primary: { DEFAULT: c("primary"), foreground: c("primary-foreground") },
        accent: { DEFAULT: c("accent"), foreground: c("accent-foreground") },
        muted: { DEFAULT: c("muted"), foreground: c("muted-foreground") },
        card: { DEFAULT: c("card"), foreground: c("card-foreground") },
        destructive: { DEFAULT: c("destructive"), foreground: c("destructive-foreground") },
        ok: c("ok"), warn: c("warn"), bad: c("bad"),
      },
      borderRadius: { lg: "1rem", md: "0.75rem", sm: "0.5rem" },
      fontFamily: { sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Inter", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
