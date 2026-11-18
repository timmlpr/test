import { AppShell } from "@/components/app-shell";

export const metadata = { robots: { index: false }, title: "Admin" };
export default function Layout({ children }: { children: React.ReactNode }) { return <AppShell>{children}</AppShell>; }
