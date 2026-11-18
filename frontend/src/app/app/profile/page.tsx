"use client";
import { PageHeader } from "@/components/page-header";
import { Identifiers } from "@/components/app/identifiers";
import { Alert } from "@/components/ui/misc";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Profile() {
  const { t } = useT();
  const { user } = useAuth();
  return (
    <div>
      <PageHeader title={t("profile.title")} explain={t("profile.explain")} next={{ label: t("onb.scanNow"), href: "/app/scan" }} />
      {!user?.email_verified && <Alert kind="warn" className="mb-4">{t("next.verify_email")} <button className="underline" onClick={() => api("/auth/resend-verification", { method: "POST" })}>Link erneut senden</button></Alert>}
      <Identifiers />
    </div>
  );
}
