"""SMS provider adapter for phone ownership codes. seven.io (Germany) as default; swappable via SMS_PROVIDER.

Docs (checked 2026-11-19): POST https://gateway.seven.io/api/sms, header X-Api-Key, params to/text/from,
JSON `success == "100"` means accepted. The phone number is only sent to the provider – never logged.
"""
from __future__ import annotations

from app.adapters.base import Adapter, AdapterMeta, SourceUnavailable
from app.settings import get_settings


class SevenSms(Adapter):
    meta = AdapterMeta(name="sms_seven", label="seven.io SMS", modules=["profile"], terms_url="https://www.seven.io/de/agb/",
                       data_types=["phone"], requires_key=True, paid=True, key_env="SMS_API_KEY", rate_per_day=500,
                       signup_url="https://app.seven.io/signup", notes="Pay per SMS (EU provider). Used only for phone ownership codes.")

    def key(self) -> str | None:
        return super().key() or get_settings().sms_api_key or None

    def send(self, to: str, text: str) -> None:
        k = self.require_key()
        r = self.http("POST", "https://gateway.seven.io/api/sms", headers={"X-Api-Key": k, "Accept": "application/json"},
                      data={"to": to, "text": text, "from": get_settings().sms_sender}, retries=1)
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        try:
            ok = str(r.json().get("success")) == "100"
        except ValueError:
            ok = r.text.strip() == "100"
        if not ok:
            raise SourceUnavailable(self.meta.name, "rejected")


PROVIDERS = {"seven": SevenSms}


def sms_provider() -> Adapter | None:
    cls = PROVIDERS.get(get_settings().sms_provider)
    return cls() if cls else None
